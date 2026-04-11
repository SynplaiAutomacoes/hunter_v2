from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView, UpdateView

from apps.finance.forms.emission_ui import format_money
from apps.finance.models.bank_account import BankAccount
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.services.reports import FinancialOverview, build_financial_overview, build_monthly_financial_overview, build_yearly_financial_overview
from apps.workorder.models import WorkOrder
from apps.workshops.mixin import WorkshopScopedMixin


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
            .order_by("-criado_em", "-pk")
        )
        return self._apply_report_filters(queryset)

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

    def _get_filter_params(self) -> dict[str, Any]:
        return {
            "start_date": self._parse_date_param(self.request.GET.get("data_inicial")),
            "end_date": self._parse_date_param(self.request.GET.get("data_final")),
            "budget_plan_ids": self._get_selected_financial_group_ids(),
            "bank_account_id": self._get_selected_bank_account_id(),
            "direction": self._get_selected_direction(),
        }

    def _apply_report_filters(self, queryset):
        filter_params = self._get_filter_params()
        start_date = filter_params["start_date"]
        end_date = filter_params["end_date"]
        budget_plan_ids = filter_params["budget_plan_ids"]
        bank_account_id = filter_params["bank_account_id"]
        direction = filter_params["direction"]

        if start_date is not None:
            queryset = queryset.filter(due_date__gte=start_date)
        if end_date is not None:
            queryset = queryset.filter(due_date__lte=end_date)
        if budget_plan_ids:
            queryset = queryset.filter(budget_plan_id__in=budget_plan_ids)
        if bank_account_id is not None:
            queryset = queryset.filter(bank_account_id=bank_account_id)
        if direction:
            queryset = queryset.filter(direction=direction)

        from django.db.models import Q
        search = str(self.request.GET.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search) |
                Q(items_observation__icontains=search) |
                Q(financial_observation__icontains=search) |
                Q(nf_number__icontains=search) |
                Q(source__name__icontains=search) |
                Q(budget_plan__name__icontains=search) |
                Q(bank_account__bank_name__icontains=search) |
                Q(workorder__id__icontains=search)
            )

        return queryset

    def _get_financial_groups_queryset(self):
        return FinancialGroup.objects.filter(workshop=self.workshop).order_by("sort_key", "id")

    def _get_bank_accounts_queryset(self):
        return BankAccount.objects.filter(workshop=self.workshop).order_by("bank_name", "account_number", "id")

    def _has_active_filters(self) -> bool:
        filter_params = self._get_filter_params()
        return bool(filter_params["start_date"] or filter_params["end_date"] or filter_params["budget_plan_ids"] or filter_params["bank_account_id"] is not None or filter_params["direction"])

    def _build_selection_summary_card(self) -> dict[str, object]:
        return self._build_summary_card(
            title="Créditos e Débitos de Seleção",
            overview=build_financial_overview(workshop=self.workshop, **self._get_filter_params()),
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
            "edit_modal_url": reverse("finance:report_movement_edit", kwargs={"pk": movement.pk}),
            "total": movement.report_total_display,
            "details": details,
        }

    def _build_pagination_url(self, *, page_number: int) -> str:
        params = self.request.GET.copy()
        params["page"] = str(page_number)
        querystring = params.urlencode()
        return f"{self.request.path}?{querystring}" if querystring else self.request.path

    def _get_financial_movements_page(self) -> tuple[Any, Paginator]:
        paginator = Paginator(self._get_financial_movements_queryset(), self.MOVEMENTS_PER_PAGE)
        page_obj = paginator.get_page(self.request.GET.get("page") or "1")
        return page_obj, paginator

    def _get_financial_movement_report_rows(self, *, movements: Any) -> list[dict[str, object]]:
        return [self._build_financial_movement_row(movement) for movement in movements]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        reference_date = timezone.localdate()
        monthly_overview = build_monthly_financial_overview(workshop=self.workshop, reference_date=reference_date)
        yearly_overview = build_yearly_financial_overview(workshop=self.workshop, reference_date=reference_date)
        filter_params = self._get_filter_params()
        page_obj, paginator = self._get_financial_movements_page()

        context["top_summary_cards"] = [
            self._build_summary_card(title="Créditos e Débitos deste Mês", overview=monthly_overview),
            self._build_summary_card(title=f"Balanço Geral {reference_date.year}", overview=yearly_overview),
            self._build_selection_summary_card(),
        ]
        context["financial_movement_report_rows"] = self._get_financial_movement_report_rows(movements=page_obj.object_list)
        context["financial_group_filters"] = self._get_financial_groups_queryset()
        context["bank_account_filters"] = self._get_bank_accounts_queryset()
        context["direction_filter_choices"] = self.FILTER_DIRECTION_CHOICES
        context["selected_financial_group_ids"] = set(filter_params["budget_plan_ids"])
        context["selected_bank_account_id"] = filter_params["bank_account_id"]
        context["selected_direction"] = filter_params["direction"]
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
        return context

    def form_valid(self, form):
        self.object = form.save()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Refresh"] = "true"
            return response
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("finance:reports_home")
