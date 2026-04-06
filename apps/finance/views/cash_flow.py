from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from apps.finance.forms.emission_ui import format_money
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.services.reports import build_financial_overview
from apps.workorder.models import WorkOrder
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
        }

    @staticmethod
    def _resolve_workorder_description(workorder: WorkOrder) -> str:
        budget = getattr(workorder, "budget", None)
        if budget is None:
            return "-"
        return str(budget.problem_description or budget.notes or "-")

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
        queryset = (
            FinancialMovement.objects.filter(workshop=self.workshop)
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
        # Apply filters
        filter_params = self._get_filter_params()
        start_date = filter_params["start_date"]
        end_date = filter_params["end_date"]

        if start_date is not None:
            queryset = queryset.filter(due_date__gte=start_date)
        if end_date is not None:
            queryset = queryset.filter(due_date__lte=end_date)
            
        return queryset

    def _build_financial_movement_row(self, movement: FinancialMovement, filter_start_date: date | None, filter_end_date: date | None) -> dict[str, object] | None:
        workorder = getattr(movement, "workorder", None)
        payment_manager = getattr(workorder, "payments", None)
        payments = list(payment_manager.all()) if payment_manager is not None else []
        customer = getattr(getattr(workorder, "budget", None), "customer", None) if workorder is not None else None

        if movement.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT and workorder is not None:
            paid_payments = [p for p in payments if p.due_date is not None and getattr(getattr(p, "total_paid", None), "amount", Decimal("0.00")) > 0]
            
            # Filter payments by Date Period if any filters apply to the movement listing
            if filter_start_date:
                paid_payments = [p for p in paid_payments if p.due_date >= filter_start_date]
            if filter_end_date:
                paid_payments = [p for p in paid_payments if p.due_date <= filter_end_date]
                
            if not paid_payments:
                return None # Skipped, no paid portion in this timeframe
                
            latest_payment_date = max((payment.due_date for payment in paid_payments), default=None)
            total_paid = sum((self._resolve_money_amount(payment.total_paid) for payment in paid_payments), start=Decimal("0.00"))
            
            due_date = latest_payment_date
            agent = getattr(customer, "name", "-") or "-"
            origin = f"OS #{workorder.pk}"
            description = self._resolve_workorder_description(workorder)
            payment_type = self._resolve_payment_method_summary(paid_payments)
            
            details = []
            remaining_amount = self._resolve_money_amount(workorder.total_budget_value)
            for payment in paid_payments:
                payment_amount = self._resolve_money_amount(payment.total_paid)
                remaining_amount = max(Decimal("0.00"), remaining_amount - payment_amount)
                details.append({
                    "payment_date": payment.due_date,
                    "payment_type": getattr(getattr(payment, "payment_method", None), "description", "-") or "-",
                    "amount": format_money(payment.total_paid),
                })
                
            return {
                "component": f"financial-movement-{movement.pk}",
                "is_expandable": bool(details),
                "type_badge": movement.report_direction_badge,
                "due_date": due_date,
                "agent": agent,
                "origin": origin,
                "description": description,
                "budget_plan": movement.report_budget_plan_display,
                "account": movement.report_bank_account_display,
                "payment_type": payment_type,
                "edit_url": reverse("finance:financial_movement_update", kwargs={"pk": movement.pk}),
                "total": {
                    "text": f"+ {format_money(total_paid)}",
                    "class": "text-success font-semibold whitespace-nowrap",
                },
                "details": details,
            }

        # Normal payments (Non-Workorder) or just simple ones
        if not movement.is_paid:
            return None # Must be paid
            
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
        for movement in self._get_financial_movements_queryset():
            row = self._build_financial_movement_row(movement, filter_params["start_date"], filter_params["end_date"])
            if row is not None:
                rows.append(row)
        return rows

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter_params = self._get_filter_params()
        
        # Saldo geral, do inicio até o dia atual (ou melhor, sem end_date para ser até o infinito)
        general_overview = build_financial_overview(
            workshop=self.workshop,
            start_date=self.workshop.criado_em.date() if self.workshop.criado_em else date(2000, 1, 1),
            end_date=None
        )

        context["saldo_atual"] = {
            "value": format_money(general_overview.confirmed_result),
            "tone": self._resolve_result_tone(general_overview.confirmed_result),
        }
        context["filter_start_date"] = filter_params["start_date"]
        context["filter_end_date"] = filter_params["end_date"]
        context["financial_movement_report_rows"] = self._get_financial_movement_report_rows()
        context["clear_filters_url"] = reverse("finance:cash_flow")
        return context
