from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DeleteView, TemplateView, UpdateView, View
from django.db import transaction
from django.db.models import Q, Value
from django.db.models.functions import Coalesce
from typing import List, Tuple

from apps.core.infrastructure.search import build_text_search_query
from apps.accounts.models import User
from apps.collaborators.models import WorkshopCollaborator
from apps.collaborators.services import delete_payroll_component_and_recalculate, recalculate_payroll_from_linked_movements, sync_workorder_collaborator_payrolls
from apps.core.presentation.widgets import SearchableSelectInput
from apps.core.workorder_numbers import format_workorder_reference
from apps.finance.forms.emission_ui import format_money
from apps.finance.models.bank_account import BankAccount
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.payroll_visibility import resolve_payroll_movement_display
from apps.finance.services.reports import build_day_month_year_financial_overviews_with_open_workorder_credits, open_credits, open_debits
from apps.finance.services.workorder_financial_movements import build_workorder_revenue_description
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod
from apps.workshops.mixin import WorkshopScopedMixin


import logging


logger = logging.getLogger(__name__)


class FinancialReportsHomeView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = FinancialMovement
    template_name = "finance/reports/reports_home.html"
    workshop_permission_codename = "view_financialmovement"
    MOVEMENTS_PER_PAGE = 10
    FILTER_DIRECTION_CHOICES = (
        ("", "Todos"),
        (FinancialMovement.MovementDirection.CREDIT, "Contas a receber"),
        (FinancialMovement.MovementDirection.DEBIT, "Contas a pagar"),
    )
    FILTER_PAID_STATUS_CHOICES = (
        ("", "Todos"),
        ("paid", "Pagos"),
        ("unpaid", "Não pagos"),
    )
    FILTER_RECONCILIATION_STATUS_CHOICES = (
        ("", "Todos"),
        ("reconciled", "Conciliados"),
        ("pending", "Aguardando conciliação"),
    )

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

    @staticmethod
    def _resolve_paid_status(*, total_paid: Decimal, total_amount: Decimal) -> dict[str, str]:
        label = {"label": "Parcial", "icon": "schedule", "class": "text-warning"}

        if total_paid <= Decimal("0.00"):
            label = {"label": "Não", "icon": "cancel", "class": "text-error"}

        if total_paid >= total_amount > Decimal("0.00"):
            label = {"label": "Sim", "icon": "check_circle", "class": "text-success"}

        return label

    @staticmethod
    def _resolve_workorder_conciliation_status(*, is_reconciled: bool) -> dict[str, str]:
        if is_reconciled:
            return {"label": "Conciliado", "icon": "check_circle", "class": "text-info"}
        return {"label": "Aguardando Conciliação", "icon": "schedule", "class": "text-warning"}

    @staticmethod
    def _resolve_simple_paid_status(*, is_paid: bool) -> dict[str, str]:
        if is_paid:
            return {"label": "Sim", "icon": "check_circle", "class": "text-success"}
        return {"label": "Não", "icon": "cancel", "class": "text-error"}

    def _resolve_movement_paid_status_display(self, movement: FinancialMovement) -> dict[str, str]:
        return self._resolve_simple_paid_status(is_paid=bool(movement.is_paid))

    @staticmethod
    def _resolve_workorder_description(workorder: WorkOrder) -> str:
        if getattr(workorder, "budget", None) is None:
            return "-"
        return build_workorder_revenue_description(workorder=workorder)

    @staticmethod
    def _resolve_payment_method_summary(payments: list[object]) -> str:
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

    def _get_financial_movements_queryset(self):
        cached = getattr(self, "_financial_movements_queryset_cache", None)
        if cached is not None:
            return cached

        queryset = (
            FinancialMovement.objects.filter(workshop=self.workshop)
            .filter(due_date__isnull=False)
            .filter(Q(movement_group__isnull=True) | Q(movement_kind=FinancialMovement.MovementKind.GROUP_PARENT))
            .exclude(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder_payment__isnull=False)
            .select_related(
                "source",
                "supplier",
                "collaborator",
                "budget_plan",
                "bank_account",
                "payment_method",
                "movement_group",
                "workorder",
                "workorder__budget",
                "workorder__budget__customer",
            )
            .prefetch_related(
                "workorder__payments",
                "workorder__payments__payment_method",
                "movement_group__financial_movements",
            )
            .annotate(
                agent_name_sort=Coalesce(
                    "collaborator__name",
                    "supplier__name",
                    "workorder__budget__customer__name",
                    "source__name",
                    Value(""),
                )
            )
            .order_by("-pk")
        )
        queryset = self._apply_report_filters(queryset)
        self._financial_movements_queryset_cache = queryset
        return queryset

    def _parse_date_param(self, raw_value: str | None) -> date | None:
        value = str(raw_value or "").strip()
        if not value:
            return None

        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _get_selected_financial_group_ids(self) -> list[int]:
        selected_group_ids: list[int] = []
        for raw_value in self.request.GET.getlist("financial_groups"):
            value = str(raw_value).strip()
            if not value:
                continue
            try:
                selected_group_ids.append(int(value))
            except (TypeError, ValueError):
                continue
        return selected_group_ids

    def _get_selected_bank_account_id(self) -> int | None:
        raw_value = str(self.request.GET.get("bank_account") or "").strip()
        if not raw_value:
            return None

        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    def _get_selected_direction(self) -> str:
        selected_direction = str(self.request.GET.get("direction") or "").strip()
        allowed_directions = {choice[0] for choice in self.FILTER_DIRECTION_CHOICES if choice[0]}
        if selected_direction not in allowed_directions:
            return ""
        return selected_direction

    def _get_search_value(self) -> str:
        return str(self.request.GET.get("search") or "").strip()

    def _get_paid_status_filter(self) -> str:
        selected_paid_status = str(self.request.GET.get("paid_status") or "").strip()
        allowed_statuses = {choice[0] for choice in self.FILTER_PAID_STATUS_CHOICES if choice[0]}
        if selected_paid_status not in allowed_statuses:
            return ""
        return selected_paid_status

    def _get_agent_filter(self) -> str:
        return str(self.request.GET.get("agent") or "").strip()

    def _get_opened_by_filter(self) -> int | None:
        raw_value = str(self.request.GET.get("opened_by") or "").strip()
        if not raw_value:
            return None
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    def _get_payment_method_filter(self) -> int | None:
        raw_value = str(self.request.GET.get("payment_method") or "").strip()
        if not raw_value:
            return None
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    def _get_reconciliation_status_filter(self) -> str:
        selected_reconciliation_status = str(self.request.GET.get("reconciliation_status") or "").strip()
        allowed_statuses = {choice[0] for choice in self.FILTER_RECONCILIATION_STATUS_CHOICES if choice[0]}
        if selected_reconciliation_status not in allowed_statuses:
            return ""
        return selected_reconciliation_status

    def _get_filter_params(self) -> dict[str, Any]:
        return {
            "start_date": self._parse_date_param(self.request.GET.get("data_inicial")),
            "end_date": self._parse_date_param(self.request.GET.get("data_final")),
            "budget_plan_ids": self._get_selected_financial_group_ids(),
            "bank_account_id": self._get_selected_bank_account_id(),
            "direction": self._get_selected_direction(),
            "paid_status": self._get_paid_status_filter(),
            "agent": self._get_agent_filter(),
            "opened_by_id": self._get_opened_by_filter(),
            "payment_method_id": self._get_payment_method_filter(),
            "reconciliation_status": self._get_reconciliation_status_filter(),
        }

    def _get_resolved_filter_params(self) -> dict[str, Any]:
        filter_params = self._get_filter_params()
        if filter_params["start_date"] is None and filter_params["end_date"] is None:
            today = timezone.localdate()
            filter_params["start_date"] = today
            filter_params["end_date"] = today
        return filter_params

    def _apply_paid_status_filter(self, queryset, paid_status: str):
        if not paid_status:
            return queryset

        matched_ids = list(queryset.exclude(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False).filter(is_paid=paid_status == "paid").values_list("pk", flat=True))

        workorder_parent_movements = queryset.filter(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False)
        for movement in workorder_parent_movements:
            if paid_status == "paid" and movement.is_paid:
                matched_ids.append(movement.pk)
            if paid_status == "unpaid" and not movement.is_paid:
                matched_ids.append(movement.pk)

        return queryset.filter(pk__in=matched_ids)

    def _apply_workorder_payment_aware_date_filter(self, queryset, *, lookup: str, value: date):
        workorder_parent_query = Q(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False)
        workorder_parent_aggregate_query = workorder_parent_query & Q(workorder_payment__isnull=True)
        workorder_parent_payment_query = workorder_parent_query & Q(workorder_payment__isnull=False)
        return queryset.filter(
            (~workorder_parent_query & Q(**{lookup: value}))
            | (
                workorder_parent_aggregate_query
                & Q(
                    workorder__payments__isnull=False,
                    **{f"workorder__payments__{lookup}": value},
                )
            )
            | (workorder_parent_payment_query & Q(**{f"workorder_payment__{lookup}": value}))
        ).distinct()

    def _apply_report_filters(self, queryset):
        filter_params = self._get_resolved_filter_params()
        start_date = filter_params["start_date"]
        end_date = filter_params["end_date"]
        budget_plan_ids = filter_params["budget_plan_ids"]
        bank_account_id = filter_params["bank_account_id"]
        direction = filter_params["direction"]
        paid_status = filter_params["paid_status"]
        agent = filter_params["agent"]
        opened_by_id = filter_params["opened_by_id"]
        payment_method_id = filter_params["payment_method_id"]
        reconciliation_status = filter_params["reconciliation_status"]

        if start_date is not None:
            queryset = self._apply_workorder_payment_aware_date_filter(queryset, lookup="due_date__gte", value=start_date)

        if end_date is not None:
            queryset = self._apply_workorder_payment_aware_date_filter(queryset, lookup="due_date__lte", value=end_date)
        if budget_plan_ids:
            queryset = queryset.filter(budget_plan_id__in=budget_plan_ids)
        if bank_account_id is not None:
            queryset = queryset.filter(bank_account_id=bank_account_id)
        if direction:
            queryset = queryset.filter(direction=direction)
        if agent:
            if agent.startswith("coll_"):
                queryset = queryset.filter(collaborator_id=agent.replace("coll_", ""))
            elif agent.startswith("supp_"):
                queryset = queryset.filter(supplier_id=agent.replace("supp_", ""))
            elif agent.startswith("wo_"):
                queryset = queryset.filter(workorder_id=agent.replace("wo_", ""))
        if opened_by_id is not None:
            queryset = queryset.filter(user_id=opened_by_id)
        if payment_method_id is not None:
            queryset = queryset.filter(
                Q(payment_method_id=payment_method_id)
                | Q(
                    movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                    workorder__isnull=False,
                    workorder__payments__payment_method_id=payment_method_id,
                )
            ).distinct()
        if reconciliation_status == "reconciled":
            queryset = queryset.filter(is_reconciled=True)
        elif reconciliation_status == "pending":
            queryset = queryset.filter(is_reconciled=False)
        queryset = self._apply_paid_status_filter(queryset, paid_status)

        search = self._get_search_value()
        if search:
            search_query = build_text_search_query(
                search_value=search,
                lookups=(
                    "description",
                    "items_observation",
                    "financial_observation",
                    "nf_number",
                    "source__name",
                    "supplier__name",
                    "collaborator__name",
                    "budget_plan__name",
                    "bank_account__bank_name",
                    "workorder__budget__customer__name",
                ),
            )
            search_query = search_query | Q(workorder__id__icontains=search) if search_query.children else Q(workorder__id__icontains=search)
            queryset = queryset.filter(search_query)

        return queryset

    def _filter_workorder_payments_for_rows(self, *, payments: list[object], filter_params: dict[str, Any]) -> list[object]:
        filtered_payments = []
        payment_movement_by_payment_id: dict[int, FinancialMovement] = getattr(self, "_payment_movement_by_payment_id", {})
        start_date = filter_params["start_date"]
        end_date = filter_params["end_date"]
        payment_method_id = filter_params["payment_method_id"]
        paid_status = filter_params["paid_status"]
        reconciliation_status = filter_params["reconciliation_status"]

        if paid_status == "unpaid":
            return []

        for payment in payments:
            payment_amount = self._resolve_money_amount(payment.total_paid)
            if payment_amount <= Decimal("0.00"):
                continue
            if start_date is not None and (payment.due_date is None or payment.due_date < start_date):
                continue
            if end_date is not None and (payment.due_date is None or payment.due_date > end_date):
                continue
            if payment_method_id is not None and payment.payment_method_id != payment_method_id:
                continue
            # Fix B2: Usa cache pré-carregado para evitar N+1 queries por payment
            payment_movement = payment_movement_by_payment_id.get(payment.pk)
            if payment_movement is None:
                workorder_fallback_cache: dict[int, FinancialMovement] = getattr(self, "_workorder_fallback_movement_cache", {})
                payment_movement = workorder_fallback_cache.get(getattr(payment, "workorder_id", None))
            if payment_movement is None:
                continue
            payment_movement_by_payment_id[payment.pk] = payment_movement
            is_reconciled = bool(getattr(payment_movement, "is_reconciled", False))
            if reconciliation_status == "reconciled" and not is_reconciled:
                continue
            if reconciliation_status == "pending" and is_reconciled:
                continue
            filtered_payments.append(payment)

        self._payment_movement_by_payment_id = payment_movement_by_payment_id

        return filtered_payments

    def _build_workorder_payment_row(self, *, movement: FinancialMovement, payment: object) -> dict[str, object]:
        workorder = movement.workorder
        payment_movement_by_payment_id: dict[int, FinancialMovement] = getattr(self, "_payment_movement_by_payment_id", {})
        payment_movement = payment_movement_by_payment_id.get(payment.pk)
        if payment_movement is None:
            # Fix B3: Tenta o cache de fallback por workorder antes de ir ao banco
            workorder_fallback_cache: dict[int, FinancialMovement] = getattr(self, "_workorder_fallback_movement_cache", {})
            payment_movement = workorder_fallback_cache.get(workorder.pk if workorder is not None else None)
        if payment_movement is None:
            payment_movement = (
                FinancialMovement.objects.filter(
                    workorder=workorder,
                    workorder_payment_id=payment.pk,
                    movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                    workshop=self.workshop,
                )
                .order_by("-pk")
                .first()
            )
        if payment_movement is None:
            payment_movement = movement
        payment_method = getattr(payment, "payment_method", None)
        payment_amount = getattr(payment, "total_paid", None)
        resolved_amount = self._resolve_money_amount(payment_amount)
        workorder_url = reverse("workorder:workorder_detail", kwargs={"pk": movement.workorder_id}) if movement.workorder_id else None
        agent, description = resolve_payroll_movement_display(movement=payment_movement, user=self.request.user, workshop=self.workshop, request=self.request)

        return {
            "component": f"workorder-payment-{payment.pk}",
            "is_expandable": False,
            "paid_status": self._resolve_simple_paid_status(is_paid=bool(payment_movement.is_paid)),
            "reconciliation_status": self._resolve_workorder_conciliation_status(is_reconciled=bool(payment_movement.is_reconciled)),
            "type_badge": payment_movement.report_direction_badge,
            "entry_date": payment_movement.entry_date,
            "due_date": payment.due_date,
            "agent": agent,
            "origin": format_workorder_reference(workorder) if workorder is not None else "-",
            "description": self._resolve_workorder_description(workorder) if workorder is not None else description,
            "budget_plan": payment_movement.report_budget_plan_display,
            "account": payment_movement.report_bank_account_display,
            "payment_type": getattr(payment_method, "description", "-") or "-",
            "edit_url": reverse("finance:financial_movement_update", kwargs={"pk": payment_movement.pk}),
            "edit_modal_url": f"{reverse('finance:report_movement_edit', kwargs={'pk': payment_movement.pk})}?payment_id={payment.pk}",
            "is_workorder": True,
            "is_group_parent": False,
            "total": {
                "text": f"+ {format_money(payment_amount)}",
                "class": "text-success font-semibold whitespace-nowrap",
            },
            "has_discount": False,
            "gross_amount": format_money(payment_amount),
            "discount_amount": format_money(Decimal("0.00")),
            "details": [],
            "summary_direction": FinancialMovement.MovementDirection.CREDIT,
            "summary_amount": resolved_amount,
            "summary_is_paid": bool(payment_movement.is_paid),
            "workorder_url": workorder_url,
        }

    def _get_financial_groups_queryset(self):
        return FinancialGroup.objects.filter(workshop=self.workshop).prefetch_related("children").order_by("sort_key", "id")

    def _get_bank_accounts_queryset(self):
        return BankAccount.objects.filter(workshop=self.workshop).order_by("bank_name", "account_number", "id")

    def _has_real_filters(self) -> bool:
        filter_params = self._get_filter_params()
        return bool(
            filter_params["start_date"]
            or filter_params["end_date"]
            or filter_params["budget_plan_ids"]
            or filter_params["bank_account_id"] is not None
            or filter_params["direction"]
            or filter_params["paid_status"]
            or filter_params["agent"]
            or filter_params["opened_by_id"] is not None
            or filter_params["payment_method_id"] is not None
            or filter_params["reconciliation_status"]
        )

    def _has_active_filters(self) -> bool:
        return self._has_real_filters() or bool(self._get_search_value())

    def _build_summary_card_from_rows(self, *, title: str, rows: list[dict[str, object]]) -> dict[str, object]:
        total_credits = Decimal("0.00")
        paid_credits = Decimal("0.00")
        total_debits = Decimal("0.00")
        paid_debits = Decimal("0.00")

        for row in rows:
            amount = Decimal(str(row.get("summary_amount") or "0.00"))
            direction = row.get("summary_direction")
            is_paid = bool(row.get("summary_is_paid"))

            if direction == FinancialMovement.MovementDirection.CREDIT:
                total_credits += amount
                if is_paid:
                    paid_credits += amount
            elif direction == FinancialMovement.MovementDirection.DEBIT:
                total_debits += amount
                if is_paid:
                    paid_debits += amount

        total_result = total_credits - total_debits
        confirmed_result = paid_credits - paid_debits

        return {
            "title": title,
            "is_placeholder": False,
            "rows": [
                {"label": "Contas a receber (total)", "value": format_money(total_credits), "small": False, "tone": "credit"},
                {"label": "Contas a receber (pagas)", "value": format_money(paid_credits), "small": True, "tone": "credit"},
                {"label": "Contas a pagar (total)", "value": format_money(total_debits), "small": False, "tone": "debit"},
                {"label": "Contas a pagar (pagas)", "value": format_money(paid_debits), "small": True, "tone": "debit"},
            ],
            "results": [
                {"label": "Resultado Total", "value": format_money(total_result), "accent": True, "tone": self._resolve_result_tone(total_result)},
                {"label": "Resultado Confirmado", "value": format_money(confirmed_result), "accent": False, "tone": self._resolve_result_tone(confirmed_result)},
            ],
        }

    def _build_selection_summary_card(self, *, rows: list[dict[str, object]]) -> dict[str, object]:
        return self._build_summary_card_from_rows(title="Resumo da listagem", rows=rows)

    def _build_financial_movement_row(self, movement: FinancialMovement) -> dict[str, object]:
        workorder = getattr(movement, "workorder", None)
        payment_manager = getattr(workorder, "payments", None)
        payments = list(payment_manager.all()) if payment_manager is not None else []
        latest_payment_date = max((payment.due_date for payment in payments if payment.due_date), default=None)
        paid_status = self._resolve_movement_paid_status_display(movement)
        reconciliation_status = self._resolve_workorder_conciliation_status(is_reconciled=bool(movement.is_reconciled))
        agent, description = resolve_payroll_movement_display(movement=movement, user=self.request.user, workshop=self.workshop, request=self.request)
        due_date = movement.due_date
        payment_type = movement.report_payment_method_display
        details = []
        edit_modal_url = reverse("finance:report_movement_edit", kwargs={"pk": movement.pk})
        is_workorder = False
        is_group_parent = False
        gross_amount = movement.gross_amount or movement.amount
        adjustment_amount = movement.resolved_adjustment_amount
        workorder_url = reverse("workorder:workorder_detail", kwargs={"pk": movement.workorder_id}) if movement.workorder_id else None

        if movement.workorder_id:
            is_workorder = True

        if workorder is not None and movement.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT:
            reconciliation_status = self._resolve_workorder_conciliation_status(is_reconciled=bool(movement.is_reconciled))
            due_date = latest_payment_date
            description = self._resolve_workorder_description(workorder)
            payment_type = self._resolve_payment_method_summary(payments)
            selected_payment_id = str(movement.workorder_payment_id) if movement.workorder_payment_id else ""
            if not selected_payment_id and payments:
                selected_payment_id = str(payments[0].pk)
            if selected_payment_id:
                edit_modal_url = f"{edit_modal_url}?payment_id={selected_payment_id}"
        elif movement.workorder_id and movement.workorder_payment_id:
            edit_modal_url = f"{edit_modal_url}?payment_id={movement.workorder_payment_id}"
        elif movement.movement_kind == FinancialMovement.MovementKind.GROUP_PARENT and movement.movement_group_id:
            is_group_parent = True
            children = movement.movement_group.financial_movements.exclude(pk=movement.pk)
            for child in children:
                details.append(
                    {
                        "payment_date": child.due_date,
                        "payment_type": child.description or "-",
                        "amount": format_money(child.amount),
                        "pending_amount": "Pago" if child.is_paid else "Pendente",
                        "pending_class": "text-success" if child.is_paid else "text-warning",
                    }
                )

        return {
            "component": f"financial-movement-{movement.pk}",
            "is_expandable": bool(details),
            "paid_status": paid_status,
            "reconciliation_status": reconciliation_status,
            "type_badge": movement.report_direction_badge,
            "entry_date": movement.entry_date,
            "due_date": due_date,
            "agent": agent,
            "origin": movement.report_origin_display if not movement.workorder_id else format_workorder_reference(movement.workorder),
            "description": description,
            "budget_plan": movement.report_budget_plan_display,
            "account": movement.report_bank_account_display,
            "payment_type": payment_type,
            "edit_url": reverse("finance:financial_movement_update", kwargs={"pk": movement.pk}),
            "edit_modal_url": edit_modal_url,
            "is_workorder": is_workorder,
            "is_group_parent": is_group_parent,
            "total": movement.report_total_display,
            "has_discount": Decimal(str(adjustment_amount.amount or 0)) > 0,
            "gross_amount": format_money(gross_amount),
            "discount_amount": format_money(adjustment_amount),
            "adjustment_label": movement.adjustment_label,
            "adjustment_is_surcharge": movement.discount_mode == FinancialMovement.DiscountMode.SURCHARGE,
            "details": details,
            "summary_direction": movement.direction,
            "summary_amount": self._resolve_money_amount(movement.amount),
            "summary_is_paid": bool(movement.is_paid),
            "workorder_url": workorder_url,
        }

    def _build_pagination_url(self, *, page_number: int) -> str:
        params = self.request.GET.copy()
        params["page"] = str(page_number)
        querystring = params.urlencode()
        return f"{self.request.path}?{querystring}" if querystring else self.request.path

    def _get_financial_movements_page(self, *, entry_refs: list[tuple[str, int]]) -> tuple[Any, Paginator]:
        page_number = self.request.GET.get("page") or "1"

        if self._has_active_filters():
            per_page = len(entry_refs) or 1
            paginator = Paginator(entry_refs, per_page)
            return paginator.get_page(page_number), paginator

        paginator = Paginator(entry_refs, self.MOVEMENTS_PER_PAGE)
        page_obj = paginator.get_page(page_number)
        return page_obj, paginator

    def _build_fallback_payment_movements_queryset(self, *, excluded_workorder_ids: set[int]):
        queryset = self._apply_report_filters(
            FinancialMovement.objects.filter(
                workshop=self.workshop,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                workorder__isnull=False,
                workorder_payment__isnull=False,
            )
            .exclude(workorder_id__in=excluded_workorder_ids)
            .select_related(
                "source",
                "supplier",
                "collaborator",
                "budget_plan",
                "bank_account",
                "payment_method",
                "workorder",
                "workorder__budget",
                "workorder__budget__customer",
                "workorder_payment",
                "workorder_payment__payment_method",
            )
            .order_by("-pk")
        )
        return queryset

    def _get_report_entry_refs(self) -> list[tuple[str, int]]:
        cached = getattr(self, "_report_entry_refs_cache", None)
        if cached is not None:
            return cached

        base_queryset = self._get_financial_movements_queryset()
        base_entries = list(base_queryset.values_list("pk", "workorder_id", "movement_kind"))
        parent_workorder_ids = {int(workorder_id) for _, workorder_id, movement_kind in base_entries if movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT and workorder_id is not None}
        entry_refs = [("movement", int(pk)) for pk, _, _ in base_entries]

        fallback_ids = list(self._build_fallback_payment_movements_queryset(excluded_workorder_ids=parent_workorder_ids).values_list("pk", flat=True))
        entry_refs.extend(("fallback", int(pk)) for pk in fallback_ids)
        entry_refs.sort(key=lambda item: item[1], reverse=True)
        self._report_entry_refs_cache = entry_refs
        return entry_refs

    def _get_paginated_report_movements(self, *, entry_refs: list[tuple[str, int]]) -> list[FinancialMovement]:
        movement_ids = [entry_id for entry_type, entry_id in entry_refs if entry_type == "movement"]
        fallback_ids = [entry_id for entry_type, entry_id in entry_refs if entry_type == "fallback"]

        movements_by_id: dict[tuple[str, int], FinancialMovement] = {}
        if movement_ids:
            base_queryset = self._get_financial_movements_queryset().filter(pk__in=movement_ids)
            for movement in base_queryset:
                movements_by_id[("movement", int(movement.pk))] = movement

        if fallback_ids:
            for movement in self._build_fallback_payment_movements_queryset(excluded_workorder_ids=set()).filter(pk__in=fallback_ids):
                movements_by_id[("fallback", int(movement.pk))] = movement

        return [movements_by_id[key] for key in entry_refs if key in movements_by_id]

    def _get_agent_filter_choices(self) -> List[Tuple[str, str]]:
        collaborators = WorkshopCollaborator.objects.filter(workshop=self.workshop, is_active=True).order_by("name")

        choices = [("", "Todos os colaboradores")]
        for c in collaborators:
            choices.append((f"coll_{c.pk}", c.name))
        return choices

    def _get_opened_by_filter_choices(self) -> List[Tuple[str, str]]:
        users = User.objects.filter(workshops=self.workshop).order_by("first_name", "last_name", "username")
        choices = [("", "Todos os usuários")]
        for u in users:
            full_name = u.get_full_name().strip()
            label = full_name if full_name else u.username
            choices.append((str(u.pk), label))
        return choices

    def _get_payment_method_filter_choices(self) -> List[Tuple[str, str]]:
        payment_methods = PaymentMethod.objects.filter(workshop=self.workshop, is_active=True).order_by("description")
        choices = [("", "Todas as formas")]
        for pm in payment_methods:
            choices.append((str(pm.pk), pm.description))
        return choices

    def _preload_payment_movement_cache(self, movement_list: list) -> None:
        """Fix B1: Pré-carrega movimentos por payment_id e workorder_id em batch para evitar N+1 queries."""
        all_payment_ids: list[int] = []
        all_workorder_ids: list[int] = []

        for movement in movement_list:
            if movement.movement_kind != FinancialMovement.MovementKind.WORKORDER_PARENT:
                continue
            workorder = getattr(movement, "workorder", None)
            if workorder is None:
                continue
            # workorder.payments.all() usa o prefetch_related já carregado — sem query extra
            for payment in workorder.payments.all():
                all_payment_ids.append(payment.pk)
            if movement.workorder_id:
                all_workorder_ids.append(movement.workorder_id)

        payment_movement_cache: dict[int, FinancialMovement] = {}
        if all_payment_ids:
            for m in FinancialMovement.objects.filter(
                workorder_payment_id__in=all_payment_ids,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                workshop=self.workshop,
            ).order_by("-pk"):
                if m.workorder_payment_id not in payment_movement_cache:
                    payment_movement_cache[m.workorder_payment_id] = m

        workorder_fallback_cache: dict[int, FinancialMovement] = {}
        if all_workorder_ids:
            for m in FinancialMovement.objects.filter(
                workorder_id__in=all_workorder_ids,
                workorder_payment__isnull=True,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                workshop=self.workshop,
            ).order_by("-pk"):
                if m.workorder_id not in workorder_fallback_cache:
                    workorder_fallback_cache[m.workorder_id] = m

        self._payment_movement_by_payment_id = payment_movement_cache
        self._workorder_fallback_movement_cache = workorder_fallback_cache

    def _get_financial_movement_report_rows(self, *, movements: Any) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        seen_components: set[str] = set()
        filter_params = self._get_resolved_filter_params()
        movement_list = list(movements)

        self._preload_payment_movement_cache(movement_list)

        for movement in movement_list:
            workorder = getattr(movement, "workorder", None)
            if workorder is not None and movement.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT:
                payments = list(workorder.payments.all())
                payment_rows = [self._build_workorder_payment_row(movement=movement, payment=payment) for payment in self._filter_workorder_payments_for_rows(payments=payments, filter_params=filter_params)]
                for payment_row in payment_rows:
                    component = str(payment_row.get("component") or "")
                    if component in seen_components:
                        continue
                    rows.append(payment_row)
                    seen_components.add(component)
                continue
            financial_row = self._build_financial_movement_row(movement)
            component = str(financial_row.get("component") or "")
            if component in seen_components:
                continue
            rows.append(financial_row)
            seen_components.add(component)
        return rows

    def _build_indicator_card(self, *, title: str, value: str, tone: str, rows: list[dict[str, str]] | None = None, filter_url: str = "") -> dict[str, Any]:
        return {
            "title": title,
            "value": value,
            "tone": tone,
            "rows": rows or [],
            "filter_url": filter_url,
        }

    def _build_card_filter_url(self, *, start_date: date, end_date: date, direction: str = "", paid_status: str = "") -> str:
        params: dict[str, str] = {
            "data_inicial": start_date.isoformat(),
            "data_final": end_date.isoformat(),
        }
        if direction:
            params["direction"] = direction
        if paid_status:
            params["paid_status"] = paid_status
        return f"{reverse('finance:reports_home')}?{urlencode(params)}"

    @staticmethod
    def _month_bounds(*, reference_date: date) -> tuple[date, date]:
        month_start = reference_date.replace(day=1)
        next_month = (reference_date.replace(day=28) + date.resolution * 4).replace(day=1)
        return month_start, next_month - date.resolution

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        reference_date = timezone.localdate()
        day_overview, month_overview, year_overview = build_day_month_year_financial_overviews_with_open_workorder_credits(workshop=self.workshop, reference_date=reference_date)
        filter_params = self._get_filter_params()
        report_entry_refs = self._get_report_entry_refs()
        page_obj, paginator = self._get_financial_movements_page(entry_refs=report_entry_refs)
        paginated_movements = self._get_paginated_report_movements(entry_refs=list(page_obj.object_list))
        page_rows = self._get_financial_movement_report_rows(movements=paginated_movements)
        listing_summary_rows = page_rows
        if not self._has_active_filters() and len(report_entry_refs) > self.MOVEMENTS_PER_PAGE:
            listing_summary_rows = self._get_financial_movement_report_rows(movements=self._get_paginated_report_movements(entry_refs=report_entry_refs))

        month_start, month_end = self._month_bounds(reference_date=reference_date)
        year_start = reference_date.replace(month=1, day=1)
        year_end = reference_date.replace(month=12, day=31)
        credit = FinancialMovement.MovementDirection.CREDIT
        debit = FinancialMovement.MovementDirection.DEBIT

        context["top_summary_cards"] = [
            self._build_indicator_card(
                title="Contas a pagar do dia",
                value=format_money(open_debits(day_overview)),
                tone="debit",
                filter_url=self._build_card_filter_url(start_date=reference_date, end_date=reference_date, direction=debit, paid_status="unpaid"),
            ),
            self._build_indicator_card(
                title="Contas a receber do dia",
                value=format_money(open_credits(day_overview)),
                tone="credit",
                filter_url=self._build_card_filter_url(start_date=reference_date, end_date=reference_date, direction=credit, paid_status="unpaid"),
            ),
            self._build_indicator_card(
                title="Contas a pagar do mês",
                value=format_money(open_debits(month_overview)),
                tone="debit",
                filter_url=self._build_card_filter_url(start_date=month_start, end_date=month_end, direction=debit, paid_status="unpaid"),
            ),
            self._build_indicator_card(
                title="Contas a receber do mês",
                value=format_money(open_credits(month_overview)),
                tone="credit",
                filter_url=self._build_card_filter_url(start_date=month_start, end_date=month_end, direction=credit, paid_status="unpaid"),
            ),
            self._build_indicator_card(
                title="Resultado do ano",
                value=format_money(year_overview.total_result),
                tone=self._resolve_result_tone(year_overview.total_result),
                filter_url=self._build_card_filter_url(start_date=year_start, end_date=year_end),
                rows=[
                    {"label": "Total a receber", "value": format_money(year_overview.total_credits), "tone": "credit", "filter_url": self._build_card_filter_url(start_date=year_start, end_date=year_end, direction=credit)},
                    {"label": "Total recebido", "value": format_money(year_overview.paid_credits), "tone": "credit", "filter_url": self._build_card_filter_url(start_date=year_start, end_date=year_end, direction=credit, paid_status="paid")},
                    {"label": "Total a pagar", "value": format_money(year_overview.total_debits), "tone": "debit", "filter_url": self._build_card_filter_url(start_date=year_start, end_date=year_end, direction=debit)},
                    {"label": "Total pago", "value": format_money(year_overview.paid_debits), "tone": "debit", "filter_url": self._build_card_filter_url(start_date=year_start, end_date=year_end, direction=debit, paid_status="paid")},
                ],
            ),
        ]
        context["selection_summary"] = self._build_selection_summary_card(rows=listing_summary_rows)
        context["financial_movement_report_rows"] = page_rows
        context["financial_group_filters"] = self._get_financial_groups_queryset()
        context["bank_account_filters"] = self._get_bank_accounts_queryset()
        context["direction_filter_choices"] = self.FILTER_DIRECTION_CHOICES
        context["paid_status_filter_choices"] = self.FILTER_PAID_STATUS_CHOICES
        context["reconciliation_status_filter_choices"] = self.FILTER_RECONCILIATION_STATUS_CHOICES
        context["selected_financial_group_ids"] = set(filter_params["budget_plan_ids"])
        context["selected_bank_account_id"] = filter_params["bank_account_id"]
        context["selected_direction"] = filter_params["direction"]
        context["selected_paid_status"] = filter_params["paid_status"]
        context["selected_reconciliation_status"] = filter_params["reconciliation_status"]

        agent_choices = self._get_agent_filter_choices()
        agent_widget = SearchableSelectInput(choices=agent_choices)
        context["agent_filter_widget"] = agent_widget.get_context(name="agent", value=filter_params["agent"], attrs={"id": "reports-filter-agent", "class": "w-full"})

        opened_by_choices = self._get_opened_by_filter_choices()
        opened_by_widget = SearchableSelectInput(choices=opened_by_choices)
        context["opened_by_filter_widget"] = opened_by_widget.get_context(name="opened_by", value=str(filter_params["opened_by_id"]) if filter_params["opened_by_id"] is not None else "", attrs={"id": "reports-filter-opened-by", "class": "w-full"})

        payment_method_choices = self._get_payment_method_filter_choices()
        payment_method_widget = SearchableSelectInput(choices=payment_method_choices)
        context["payment_method_filter_widget"] = payment_method_widget.get_context(name="payment_method", value=str(filter_params["payment_method_id"]) if filter_params["payment_method_id"] is not None else "", attrs={"id": "reports-filter-payment-method", "class": "w-full"})

        context["has_active_filters"] = self._has_active_filters()
        context["clear_filters_url"] = reverse("finance:reports_home")
        context["page_obj"] = page_obj
        context["paginator"] = paginator
        context["is_paginated"] = paginator.num_pages > 1
        context["prev_url"] = self._build_pagination_url(page_number=page_obj.previous_page_number()) if page_obj.has_previous() else None
        context["next_url"] = self._build_pagination_url(page_number=page_obj.next_page_number()) if page_obj.has_next() else None
        context["htmx_target"] = "#financial-reports-movements-section"
        context["htmx_select"] = "#financial-reports-movements-section"
        context["htmx_swap"] = "outerHTML"
        context["htmx_push_url"] = "true"
        return context


class ReportMovementEditView(LoginRequiredMixin, WorkshopScopedMixin, UpdateView):
    model = FinancialMovement
    template_name = "finance/partials/financial_movement/report_edit_movement_modal.html"
    workshop_permission_codename = "change_financialmovement"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        payroll = getattr(self.object, "collaborator_payroll", None)
        if payroll is not None:
            return HttpResponseRedirect(reverse("finance:payroll_edit_modal", kwargs={"pk": payroll.pk}))
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        payroll = getattr(self.object, "collaborator_payroll", None)
        if payroll is not None:
            return HttpResponseRedirect(reverse("finance:payroll_edit_modal", kwargs={"pk": payroll.pk}))
        return super().post(request, *args, **kwargs)

    def get_form_class(self):
        from apps.finance.forms.financial_movement import ReportMovementEditForm

        return ReportMovementEditForm

    def get_queryset(self):
        return super().get_queryset().filter(workshop=self.workshop)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        kwargs["workshop"] = self.workshop
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["movement"] = self.object
        if self.object.installment_plan_id:
            context["installments"] = self.object.installment_plan.financial_movements.order_by(
                "installment_number", "pk"
            )
        fallback_payment_id = ""
        if getattr(self.object, "workorder_payment_id", None):
            fallback_payment_id = str(self.object.workorder_payment_id)
        elif getattr(self.object, "workorder_id", None):
            first_payment = WorkOrderPaymentMethod.objects.filter(workorder_id=self.object.workorder_id).order_by("-pk").first()
            if first_payment is not None:
                fallback_payment_id = str(first_payment.pk)

        selected_workorder_payment_id = self.request.GET.get("payment_id") or self.request.POST.get("selected_workorder_payment_id") or fallback_payment_id
        context["selected_workorder_payment_id"] = selected_workorder_payment_id

        forced_payment_method_id = ""
        if getattr(self.object, "payment_method_id", None):
            forced_payment_method_id = str(self.object.payment_method_id)
        elif selected_workorder_payment_id:
            selected_payment = WorkOrderPaymentMethod.objects.filter(pk=selected_workorder_payment_id).select_related("payment_method").first()
            if selected_payment is not None and getattr(selected_payment, "payment_method_id", None):
                forced_payment_method_id = str(selected_payment.payment_method_id)
        context["forced_payment_method_id"] = forced_payment_method_id

        logger.warning(
            "[ReportMovementEditView] modal context payment | movement_id=%s kind=%s workorder_id=%s query_payment_id=%s selected_workorder_payment_id=%s movement_workorder_payment_id=%s movement_payment_method_id=%s forced_payment_method_id=%s",
            getattr(self.object, "pk", None),
            getattr(self.object, "movement_kind", None),
            getattr(self.object, "workorder_id", None),
            self.request.GET.get("payment_id"),
            context["selected_workorder_payment_id"],
            getattr(self.object, "workorder_payment_id", None),
            getattr(self.object, "payment_method_id", None),
            forced_payment_method_id,
        )
        return context

    def form_valid(self, form):
        self.object = form.save()
        payroll = getattr(self.object, "payroll", None) or getattr(self.object, "collaborator_payroll", None)
        if payroll is not None:
            recalculate_payroll_from_linked_movements(payroll=payroll)
        if self.object.workorder_id:
            sync_workorder_collaborator_payrolls(workorder=self.object.workorder, reference_date=self.object.due_date)
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Refresh"] = "true"
            return response
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:reports_home")


class ReportMovementDeleteView(LoginRequiredMixin, WorkshopScopedMixin, DeleteView):
    model = FinancialMovement
    workshop_permission_codename = "delete_financialmovement"

    def get_queryset(self):
        return super().get_queryset().filter(workshop=self.workshop)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["hx_target"] = "#edit-modal-container"
        return context

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        return render(request, "finance/partials/financial_movement/financial_movement_delete_modal.html", context)

    def form_valid(self, form):
        linked_payroll = self.object.payroll if getattr(self.object, "payroll_id", None) else None
        if linked_payroll is None and getattr(self.object, "collaborator_payroll", None) is not None:
            linked_payroll = self.object.collaborator_payroll

        if linked_payroll is not None:
            delete_payroll_component_and_recalculate(movement=self.object)
        else:
            self.object.delete()

        if self.request.htmx:
            response = HttpResponse()
            response["HX-Refresh"] = "true"
            return response
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse("finance:reports_home")


class BatchConciliateModalView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = FinancialMovement
    workshop_permission_codename = "change_financialmovement"

    def get(self, request, *args, **kwargs):
        movement_ids = [str(value) for value in request.GET.getlist("movement_ids") if str(value).strip()]
        bank_accounts = BankAccount.objects.filter(workshop=self.workshop, is_active=True).order_by("bank_name", "account_number", "id")
        return render(
            request,
            "finance/reports/partials/batch_conciliate_modal.html",
            {
                "movement_ids": movement_ids,
                "bank_accounts": bank_accounts,
            },
        )


class BatchConciliateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = FinancialMovement
    workshop_permission_codename = "change_financialmovement"

    def post(self, request, *args, **kwargs):
        raw_values = request.POST.getlist("movement_ids")
        selected_bank_account_id = str(request.POST.get("bank_account_id") or "").strip()
        logger.info("BatchConciliateView received %d movement_ids: %s", len(raw_values), raw_values)

        if not selected_bank_account_id:
            return render(
                request,
                "finance/reports/partials/batch_conciliate_errors.html",
                {
                    "errors": [{"id": "Conta bancária", "reason": "Selecione uma conta bancária para aplicar na conciliação em lote."}],
                    "success_count": 0,
                },
            )

        bank_account = get_object_or_404(BankAccount, workshop=self.workshop, pk=selected_bank_account_id)

        fm_ids = []
        wo_payment_pks: list[int] = []
        for value in raw_values:
            if value.startswith("financial-movement-"):
                try:
                    fm_ids.append(int(value.replace("financial-movement-", "")))
                except ValueError:
                    pass
            elif value.startswith("workorder-payment-"):
                try:
                    wo_payment_pks.append(int(value.replace("workorder-payment-", "")))
                except ValueError:
                    pass

        movement_map: dict[str, FinancialMovement] = {}

        if fm_ids:
            qs = FinancialMovement.objects.filter(pk__in=fm_ids, workshop=self.workshop).select_related("workorder", "workorder__budget", "workorder__budget__customer")
            for m in qs:
                movement_map[f"financial-movement-{m.pk}"] = m

        if wo_payment_pks:
            # Busca per-payment movements
            per_payment_map: dict[int, FinancialMovement] = {}
            for m in (
                FinancialMovement.objects.filter(
                    workorder_payment_id__in=wo_payment_pks,
                    movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                    workshop=self.workshop,
                )
                .select_related("workorder", "workorder__budget", "workorder__budget__customer")
                .order_by("-pk")
            ):
                key = m.workorder_payment_id
                if key is not None and key not in per_payment_map:
                    per_payment_map[key] = m

            # Busca os WorkOrderPaymentMethod faltantes para tentar fallback ao agregado
            found_pks = set(per_payment_map.keys())
            missing_pks = [pk for pk in wo_payment_pks if pk not in found_pks]
            logger.info("Per-payment movements found: %d, missing: %d", len(found_pks), len(missing_pks))

            fallback_workorder_ids: set[int] = set()
            if missing_pks:
                for pm in WorkOrderPaymentMethod.objects.filter(pk__in=missing_pks).select_related("workorder"):
                    if pm.workorder_id:
                        fallback_workorder_ids.add(pm.workorder_id)

            # Busca movimentos agregados para os workorders em fallback
            aggregate_map: dict[int, FinancialMovement] = {}
            if fallback_workorder_ids:
                for m in (
                    FinancialMovement.objects.filter(
                        workorder_id__in=list(fallback_workorder_ids),
                        movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                        workorder_payment__isnull=True,
                        workshop=self.workshop,
                    )
                    .select_related("workorder", "workorder__budget", "workorder__budget__customer")
                    .order_by("-pk")
                ):
                    wo_id = m.workorder_id
                    if wo_id is not None and wo_id not in aggregate_map:
                        aggregate_map[wo_id] = m

            # Popula movement_map: primeiro per-payment, depois fallback agregado
            for pk in wo_payment_pks:
                key = f"workorder-payment-{pk}"
                if pk in per_payment_map:
                    movement_map[key] = per_payment_map[pk]
                else:
                    pm = WorkOrderPaymentMethod.objects.filter(pk=pk).select_related("workorder").first()
                    if pm and pm.workorder_id and pm.workorder_id in aggregate_map:
                        movement_map[key] = aggregate_map[pm.workorder_id]
                        logger.info("Fallback para agregado da OS %s para workorder-payment-%s", pm.workorder_id, pk)

            if not movement_map.get(f"workorder-payment-{wo_payment_pks[0]}" if wo_payment_pks else "__dummy__"):
                logger.warning(
                    "Nenhum movimento encontrado para workorder-payment IDs %s. Per-payment: %s, missing: %s, fallback WOs: %s",
                    wo_payment_pks,
                    list(per_payment_map.keys()),
                    missing_pks,
                    list(fallback_workorder_ids),
                )

        errors = []
        validated_movements: list[FinancialMovement] = []

        for value in raw_values:
            movement = movement_map.get(value)
            if movement is None:
                errors.append({"id": value, "reason": "Nenhuma movimentação financeira encontrada para este pagamento. Execute a sincronização da O.S. primeiro."})
                continue
            if not movement.is_paid:
                errors.append({"id": self._label(movement), "reason": "O pagamento desta movimentação ainda não foi confirmado. Marque como 'Sim' no campo Pago antes de conciliar."})
                continue
            if movement.is_reconciled:
                errors.append({"id": self._label(movement), "reason": "Esta movimentação já está conciliada."})
                continue
            if not movement.budget_plan_id:
                errors.append({"id": self._label(movement), "reason": "Plano Orçamentário é obrigatório para conciliar. Preencha o campo no modal de edição."})
                continue
            validated_movements.append(movement)

        if errors:
            logger.warning("Conciliação em lote: %d erros, nenhuma movimentação foi atualizada", len(errors))
            return render(
                request,
                "finance/reports/partials/batch_conciliate_errors.html",
                {
                    "errors": errors,
                    "success_count": 0,
                },
            )

        if validated_movements:
            with transaction.atomic():
                reconciled_pks = [m.pk for m in validated_movements]
                updated = FinancialMovement.objects.filter(pk__in=reconciled_pks).update(is_reconciled=True, bank_account=bank_account)
                logger.info("Conciliação em lote: %d movimentos reconciliados (atomic)", updated)

        response = HttpResponse()
        response["HX-Refresh"] = "true"
        return response

    def _label(self, movement: FinancialMovement) -> str:
        if movement.workorder_id:
            customer = getattr(getattr(movement.workorder, "budget", None), "customer", None)
            name = customer.name if customer else ""
            reference = format_workorder_reference(movement.workorder)
            return f"{reference} — {name}" if name else reference
        return movement.description or f"Movimentação #{movement.pk}"


class FinancialBulkPayView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = FinancialMovement
    workshop_permission_codename = "change_financialmovement"

    def post(self, request, *args, **kwargs):
        raw_values = request.POST.getlist("movement_ids")
        logger.info("FinancialBulkPayView received %d movement_ids: %s", len(raw_values), raw_values)

        if not raw_values:
            return HttpResponse("Nenhuma movimentação selecionada.", status=400)

        fm_ids = []
        wo_payment_pks = []
        for value in raw_values:
            if value.startswith("financial-movement-"):
                try:
                    fm_ids.append(int(value.replace("financial-movement-", "")))
                except ValueError:
                    pass
            elif value.startswith("workorder-payment-"):
                try:
                    wo_payment_pks.append(int(value.replace("workorder-payment-", "")))
                except ValueError:
                    pass

        target_pks = set(fm_ids)

        if wo_payment_pks:
            # Encontrar movimentos associados aos pagamentos de OS
            wo_movements = FinancialMovement.objects.filter(workshop=self.workshop, workorder_payment_id__in=wo_payment_pks, movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT).values_list("pk", flat=True)
            target_pks.update(list(wo_movements))

        if target_pks:
            with transaction.atomic():
                updated = FinancialMovement.objects.filter(pk__in=target_pks, workshop=self.workshop, is_paid=False).update(is_paid=True)
                logger.info("Bulk Pay: %d movements marked as paid", updated)

        if request.headers.get("HX-Request"):
            response = HttpResponse()
            response["HX-Refresh"] = "true"
            return response

        return HttpResponseRedirect(reverse("finance:reports_home"))
