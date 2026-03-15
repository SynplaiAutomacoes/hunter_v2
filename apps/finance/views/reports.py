from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from apps.finance.forms.emission_ui import format_money
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.services.reports import FinancialOverview, build_monthly_financial_overview, build_yearly_financial_overview
from apps.workorder.models import WorkOrder
from apps.workshops.mixin import WorkshopScopedMixin


class FinancialReportsHomeView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = FinancialMovement
    template_name = "finance/reports/reports_home.html"
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

    @staticmethod
    def _resolve_paid_status(*, total_paid: Decimal, total_amount: Decimal) -> dict[str, str]:
        if total_paid <= Decimal("0.00"):
            return {"label": "Não", "icon": "cancel", "class": "text-error"}
        if total_paid >= total_amount and total_amount > Decimal("0.00"):
            return {"label": "Sim", "icon": "check_circle", "class": "text-success"}
        return {"label": "Parcial", "icon": "schedule", "class": "text-warning"}

    def _build_summary_card(self, *, title: str, overview: FinancialOverview) -> dict[str, object]:
        return {
            "title": title,
            "is_placeholder": False,
            "rows": [
                {"label": "Créditos Totais", "value": format_money(overview.total_credits), "small": False, "tone": "credit"},
                {"label": "Créditos Pagos", "value": format_money(overview.paid_credits), "small": True, "tone": "credit"},
                {"label": "Débitos Totais", "value": format_money(overview.total_debits), "small": False, "tone": "debit"},
                {"label": "Débitos Pagos", "value": format_money(overview.paid_debits), "small": True, "tone": "debit"},
            ],
            "results": [
                {"label": "Resultado Total", "value": format_money(overview.total_result), "accent": True, "tone": self._resolve_result_tone(overview.total_result)},
                {"label": "Resultado Confirmado", "value": format_money(overview.confirmed_result), "accent": False, "tone": self._resolve_result_tone(overview.confirmed_result)},
            ],
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
        return (
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
            .order_by("-criado_em", "-pk")
        )

    def _build_financial_movement_row(self, movement: FinancialMovement) -> dict[str, object]:
        workorder = getattr(movement, "workorder", None)
        payment_manager = getattr(workorder, "payments", None)
        payments = list(payment_manager.all()) if payment_manager is not None else []
        latest_payment_date = max((payment.due_date for payment in payments if payment.due_date), default=None)
        total_paid = sum((self._resolve_money_amount(payment.total_paid) for payment in payments), start=Decimal("0.00"))
        customer = getattr(getattr(workorder, "budget", None), "customer", None) if workorder is not None else None

        if workorder is not None and movement.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT:
            total_amount = self._resolve_money_amount(workorder.total_budget_value)
            paid_status: str | dict[str, str] = self._resolve_paid_status(total_paid=total_paid, total_amount=self._resolve_money_amount(workorder.total_budget_value))
            due_date = latest_payment_date
            agent = getattr(customer, "name", "-") or "-"
            origin = f"OS #{workorder.pk}"
            description = self._resolve_workorder_description(workorder)
            payment_type = self._resolve_payment_method_summary(payments)
            remaining_amount = total_amount
            details = []
            for payment in payments:
                payment_amount = self._resolve_money_amount(payment.total_paid)
                remaining_amount = max(Decimal("0.00"), remaining_amount - payment_amount)
                details.append(
                    {
                        "payment_date": payment.due_date,
                        "payment_type": getattr(getattr(payment, "payment_method", None), "description", "-") or "-",
                        "amount": format_money(payment.total_paid),
                        "pending_amount": format_money(remaining_amount),
                        "pending_class": "text-success" if remaining_amount == Decimal("0.00") else "text-warning",
                    }
                )
        elif workorder is not None:
            paid_status = movement.report_paid_indicator
            due_date = movement.due_date
            agent = getattr(customer, "name", "-") or "-"
            origin = f"OS #{workorder.pk}"
            description = movement.report_description_display
            payment_type = movement.report_payment_method_display
            details = []
        else:
            paid_status = movement.report_paid_indicator
            due_date = movement.due_date
            agent = movement.report_agent_display
            origin = movement.report_origin_display
            description = movement.report_description_display
            payment_type = movement.report_payment_method_display
            details = []

        return {
            "component": f"financial-movement-{movement.pk}",
            "is_expandable": bool(details),
            "paid_status": paid_status,
            "type_badge": movement.report_direction_badge,
            "due_date": due_date,
            "agent": agent,
            "origin": origin,
            "description": description,
            "budget_plan": movement.report_budget_plan_display,
            "account": movement.report_bank_account_display,
            "payment_type": payment_type,
            "edit_url": reverse("finance:financial_movement_update", kwargs={"pk": movement.pk}),
            "total": movement.report_total_display,
            "details": details,
        }

    def _get_financial_movement_report_rows(self) -> list[dict[str, object]]:
        return [self._build_financial_movement_row(movement) for movement in self._get_financial_movements_queryset()]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        reference_date = timezone.localdate()
        monthly_overview = build_monthly_financial_overview(workshop=self.workshop, reference_date=reference_date)
        yearly_overview = build_yearly_financial_overview(workshop=self.workshop, reference_date=reference_date)

        context["top_summary_cards"] = [
            self._build_summary_card(title="Créditos e Débitos deste Mês", overview=monthly_overview),
            self._build_summary_card(title=f"Balanço Geral {reference_date.year}", overview=yearly_overview),
            self._build_summary_card(title="Créditos e Débitos de Seleção", overview=monthly_overview),
        ]
        context["financial_movement_report_rows"] = self._get_financial_movement_report_rows()
        return context
