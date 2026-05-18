from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.views.generic import TemplateView

from django.db.models import Q
from apps.core.search import apply_text_search
from apps.finance.forms.emission_ui import format_money
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.bank_account import BankAccount
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.services.reports import build_financial_overview
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod
from apps.workshops.mixin import WorkshopScopedMixin


class CashFlowView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = FinancialMovement
    template_name = "finance/cash_flow/cash_flow.html"
    workshop_permission_codename = "view_financialmovement"

    @staticmethod
    def _resolve_result_tone(value: object) -> str:
        amount = Decimal(str(getattr(value, "amount", value) or 0))
        if amount > 0:
            return "credit"
        if amount < 0:
            return "debit"
        return "neutral"

    @staticmethod
    def _resolve_money_amount(value: object) -> Decimal:
        return Decimal(str(getattr(value, "amount", value) or 0))

    def _parse_date_param(self, raw_value: str | None) -> date | None:
        value = str(raw_value or "").strip()
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _get_filter_params(self) -> dict[str, Any]:
        return {
            "start_date": self._parse_date_param(self.request.GET.get("data_inicial")),
            "end_date": self._parse_date_param(self.request.GET.get("data_final")),
            "agent": self.request.GET.get("agente", "").strip(),
            "payment_method_id": self.request.GET.get("forma_pagamento"),
            "budget_plan_id": self.request.GET.get("plano_orcamentario"),
            "movement_type": self.request.GET.get("tipo_movimentacao"),
            "bank_account_id": self.request.GET.get("conta_bancaria"),
            "search": self.request.GET.get("search", "").strip(),
        }

    @staticmethod
    def _resolve_workorder_description(workorder: WorkOrder) -> str:
        budget = getattr(workorder, "budget", None)
        if budget is None:
            return "-"
        return str(budget.problem_description or budget.notes or "-")

    @staticmethod
    def _resolve_payment_method_summary(payments: list[WorkOrderPaymentMethod]) -> str:
        method_names: list[str] = []
        for payment in payments:
            payment_method = getattr(payment, "payment_method", None)
            description = getattr(payment_method, "description", None)
            if description and description not in method_names:
                method_names.append(str(description))

        if not method_names:
            return "-"
        if len(method_names) == 1:
            return method_names[0]
        return "Múltiplos"

    def _apply_workorder_payment_aware_date_filter(self, queryset, *, lookup: str, value: date):
        return queryset.filter(
            Q(**{lookup: value})
            | Q(
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                workorder__isnull=False,
                workorder__payments__isnull=False,
                **{f"workorder__payments__{lookup}": value},
            )
        ).distinct()

    def _get_financial_movements_queryset(self):
        queryset = (
            FinancialMovement.objects.filter(workshop=self.workshop)
            .filter(Q(movement_group__isnull=True) | Q(movement_kind=FinancialMovement.MovementKind.GROUP_PARENT))
            .select_related(
                "source",
                "budget_plan",
                "bank_account",
                "payment_method",
                "workorder",
                "workorder__budget",
                "workorder__budget__customer",
            )
            .prefetch_related("workorder__payments", "workorder__payments__payment_method")
            .order_by("-due_date", "-pk")
        )

        filter_params = self._get_filter_params()

        # Date Filters
        if filter_params["start_date"]:
            queryset = self._apply_workorder_payment_aware_date_filter(queryset, lookup="due_date__gte", value=filter_params["start_date"])
        if filter_params["end_date"]:
            queryset = self._apply_workorder_payment_aware_date_filter(queryset, lookup="due_date__lte", value=filter_params["end_date"])

        # Agent Filter
        if filter_params["agent"]:
            queryset = apply_text_search(queryset, search_value=filter_params["agent"], lookups=("source__name", "workorder__budget__customer__name"))

        # Payment Method Filter
        if filter_params["payment_method_id"]:
            pm_filter = Q(payment_method_id=filter_params["payment_method_id"]) | Q(
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                workorder__isnull=False,
                workorder__payments__payment_method_id=filter_params["payment_method_id"],
            )
            queryset = queryset.filter(pm_filter).distinct()

        # Budget Plan Filter
        if filter_params["budget_plan_id"]:
            queryset = queryset.filter(budget_plan_id=filter_params["budget_plan_id"])

        # Movement Type Filter (Credit/Debit)
        if filter_params["movement_type"]:
            queryset = queryset.filter(direction=filter_params["movement_type"])

        # Bank Account Filter
        if filter_params["bank_account_id"]:
            if filter_params["bank_account_id"] == "none":
                queryset = queryset.filter(bank_account__isnull=True)
            else:
                queryset = queryset.filter(bank_account_id=filter_params["bank_account_id"])

        # Global Search
        if filter_params["search"]:
            queryset = apply_text_search(queryset, search_value=filter_params["search"], lookups=("description", "source__name", "nf_number", "workorder__budget__customer__name")).distinct()

        return queryset

    def _filter_workorder_payments_for_rows(self, *, payments: list[WorkOrderPaymentMethod], filter_start_date: date | None, filter_end_date: date | None, payment_method_id: str | None, bank_account_id: str | None) -> list[WorkOrderPaymentMethod]:
        reconciled_movement_by_payment_id: dict[int, FinancialMovement] = getattr(self, "_reconciled_workorder_payment_movements", {})
        filtered_payments = []
        for payment in payments:
            payment_amount = self._resolve_money_amount(payment.total_paid)
            if payment.due_date is None or payment_amount <= Decimal("0.00"):
                continue
            if filter_start_date and payment.due_date < filter_start_date:
                continue
            if filter_end_date and payment.due_date > filter_end_date:
                continue
            if payment_method_id and str(getattr(payment.payment_method, "pk", "")) != str(payment_method_id):
                continue
            payment_movement = reconciled_movement_by_payment_id.get(payment.pk)
            if payment_movement is None:
                continue
            if bank_account_id:
                if bank_account_id == "none":
                    if payment_movement.bank_account_id is not None:
                        continue
                elif str(payment_movement.bank_account_id or "") != str(bank_account_id):
                    continue
            filtered_payments.append(payment)
        return filtered_payments

    def _build_workorder_payment_row(self, *, movement: FinancialMovement, payment: WorkOrderPaymentMethod) -> dict[str, object]:
        workorder = movement.workorder
        reconciled_movement_by_payment_id: dict[int, FinancialMovement] = getattr(self, "_reconciled_workorder_payment_movements", {})
        payment_movement = reconciled_movement_by_payment_id.get(payment.pk)
        if payment_movement is None:
            payment_movement = movement
        customer = getattr(getattr(workorder, "budget", None), "customer", None) if workorder is not None else None
        payment_method = getattr(payment_movement, "payment_method", None) or getattr(payment, "payment_method", None)

        return {
            "component": f"workorder-payment-{payment.pk}",
            "is_expandable": False,
            "type_badge": payment_movement.report_direction_badge,
            "due_date": payment.due_date,
            "agent": getattr(customer, "name", "-") or "-",
            "origin": f"OS #{workorder.pk}" if workorder is not None else "-",
            "description": self._resolve_workorder_description(workorder) if workorder is not None else movement.report_description_display,
            "budget_plan": payment_movement.report_budget_plan_display,
            "account": payment_movement.report_bank_account_display,
            "payment_type": getattr(payment_method, "description", "-") or "-",
            "edit_url": reverse("finance:financial_movement_update", kwargs={"pk": payment_movement.pk}),
            "total": {
                "text": f"+ {format_money(payment.total_paid)}",
                "class": "text-success font-semibold whitespace-nowrap",
            },
            "details": [],
        }

    def _build_financial_movement_row(self, movement: FinancialMovement, filter_start_date: date | None, filter_end_date: date | None) -> dict[str, object] | None:
        workorder = getattr(movement, "workorder", None)
        customer = getattr(getattr(workorder, "budget", None), "customer", None) if workorder is not None else None

        if movement.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT and workorder is not None:
            return None

        # Normal payments (Non-Workorder) or just simple ones
        if not movement.is_reconciled:
            return None

        return {
            "component": f"financial-movement-{movement.pk}",
            "is_expandable": False,
            "type_badge": movement.report_direction_badge,
            "due_date": movement.due_date,
            "agent": movement.report_agent_display if not workorder else (getattr(customer, "name", "-") or "-"),
            "origin": movement.report_origin_display if not workorder else f"OS #{workorder.pk}",
            "description": movement.report_description_display,
            "budget_plan": movement.report_budget_plan_display,
            "account": movement.report_bank_account_display,
            "payment_type": movement.report_payment_method_display,
            "edit_url": reverse("finance:financial_movement_update", kwargs={"pk": movement.pk}),
            "total": movement.report_total_display,
            "details": [],
        }

    def _get_financial_movement_report_rows(self) -> list[dict[str, object]]:
        filter_params = self._get_filter_params()
        rows = []
        movements = list(self._get_financial_movements_queryset())
        workorder_ids = sorted({movement.workorder.pk for movement in movements if movement.workorder is not None and movement.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT})
        reconciled_workorder_payment_movements = FinancialMovement.objects.none()
        if workorder_ids:
            reconciled_workorder_payment_movements = FinancialMovement.objects.filter(
                workshop=self.workshop,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                workorder_id__in=workorder_ids,
                workorder_payment__isnull=False,
                is_reconciled=True,
            ).select_related("payment_method", "budget_plan", "bank_account")
            bank_account_id = filter_params["bank_account_id"]
            if bank_account_id:
                if bank_account_id == "none":
                    reconciled_workorder_payment_movements = reconciled_workorder_payment_movements.filter(bank_account__isnull=True)
                else:
                    reconciled_workorder_payment_movements = reconciled_workorder_payment_movements.filter(bank_account_id=bank_account_id)

        self._reconciled_workorder_payment_movements = {movement.workorder_payment.pk: movement for movement in reconciled_workorder_payment_movements if movement.workorder_payment is not None}

        for movement in movements:
            workorder = getattr(movement, "workorder", None)
            if workorder is not None and movement.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT:
                payments = list(workorder.payments.all())
                rows.extend(
                    self._build_workorder_payment_row(movement=movement, payment=payment)
                    for payment in self._filter_workorder_payments_for_rows(
                        payments=payments,
                        filter_start_date=filter_params["start_date"],
                        filter_end_date=filter_params["end_date"],
                        payment_method_id=filter_params["payment_method_id"],
                        bank_account_id=filter_params["bank_account_id"],
                    )
                )
                continue
            row = self._build_financial_movement_row(movement, filter_params["start_date"], filter_params["end_date"])
            if row is not None:
                rows.append(row)
        return rows

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter_params = self._get_filter_params()

        bank_account_id = filter_params.get("bank_account_id")
        selected_account_name = None
        if bank_account_id:
            if bank_account_id == "none":
                selected_account_name = "Sem Vínculo"
            else:
                try:
                    selected_account = BankAccount.objects.get(pk=bank_account_id, workshop=self.workshop)
                    selected_account_name = str(selected_account)
                except (BankAccount.DoesNotExist, ValueError):
                    selected_account_name = None

        # Saldo baseado nos filtros aplicados (ou geral se nenhum filtro)
        # Se não houver data_inicial, mostramos o saldo acumulado até a data final (se houver) ou até hoje.
        general_overview = build_financial_overview(
            workshop=self.workshop,
            start_date=filter_params["start_date"],
            end_date=filter_params["end_date"],
            search=filter_params["search"],
            direction=filter_params["movement_type"],
            paid_status="paid",
            reconciliation_status="reconciled",
            budget_plan_ids=[filter_params["budget_plan_id"]] if filter_params["budget_plan_id"] else None,
            bank_account_id=bank_account_id if bank_account_id else None,
            agent=filter_params["agent"],
            payment_method_id=filter_params["payment_method_id"],
        )

        context["saldo_atual"] = {
            "value": format_money(general_overview.confirmed_result),
            "tone": self._resolve_result_tone(general_overview.confirmed_result),
            "account_name": selected_account_name,
        }
        context["filter_start_date"] = filter_params["start_date"]
        context["filter_end_date"] = filter_params["end_date"]
        context["financial_movement_report_rows"] = self._get_financial_movement_report_rows()
        context["clear_filters_url"] = reverse("finance:cash_flow")

        # Filter Choices
        context["bank_accounts"] = BankAccount.objects.filter(workshop=self.workshop).order_by("bank_name")
        context["payment_methods"] = PaymentMethod.objects.filter(workshop=self.workshop).order_by("description")
        context["budget_plans"] = FinancialGroup.objects.filter(workshop=self.workshop).order_by("sort_key")
        context["movement_types"] = FinancialMovement.MovementDirection.choices

        return context
