from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DeleteView, TemplateView, UpdateView
from django.db.models import Q, Value
from django.db.models.functions import Coalesce
from typing import List, Tuple

from apps.core.search import build_text_search_query
from apps.accounts.models import User
from apps.collaborators.models import CollaboratorCommissionEntry, CollaboratorPayroll, WorkshopCollaborator
from apps.collaborators.services import sync_workorder_collaborator_payrolls
from apps.core.widgets import SearchableSelectInput
from apps.finance.forms.emission_ui import format_money
from apps.finance.models.bank_account import BankAccount
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.reports import FinancialOverview, build_monthly_financial_overview, build_yearly_financial_overview
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
    FILTER_PAID_STATUS_CHOICES = (
        ("", "Todos"),
        ("paid", "Pagos"),
        ("unpaid", "Não pagos"),
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
    def _resolve_workorder_conciliation_status(*, is_paid: bool) -> dict[str, str]:
        if is_paid:
            return {"label": "Conciliado", "icon": "check_circle", "class": "text-success"}
        return {"label": "Aguardando Conciliação", "icon": "schedule", "class": "text-warning"}

    def _resolve_movement_paid_status_display(self, movement: FinancialMovement) -> dict[str, str]:
        if movement.movement_kind in {FinancialMovement.MovementKind.WORKORDER_PARENT, FinancialMovement.MovementKind.WORKORDER_CARD_FEE}:
            return self._resolve_workorder_conciliation_status(is_paid=bool(movement.is_paid))
        paid_status = movement.report_paid_indicator
        return paid_status if isinstance(paid_status, dict) else {"label": str(paid_status), "icon": "schedule", "class": "text-warning"}

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
            .filter(due_date__isnull=False)
            .filter(Q(movement_group__isnull=True) | Q(movement_kind=FinancialMovement.MovementKind.GROUP_PARENT))
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
            )
            .prefetch_related("workorder__payments", "workorder__payments__payment_method")
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
        }

    def _apply_paid_status_filter(self, queryset, paid_status: str):
        if not paid_status:
            return queryset

        matched_ids = list(queryset.exclude(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False).filter(is_paid=paid_status == "paid").values_list("pk", flat=True))

        workorder_parent_movements = queryset.filter(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False).select_related("workorder").prefetch_related("workorder__payments")
        for movement in workorder_parent_movements:
            payments = list(movement.workorder.payments.all())
            has_payments = any(self._resolve_money_amount(payment.total_paid) > Decimal("0.00") for payment in payments)
            if paid_status == "paid" and has_payments:
                matched_ids.append(movement.pk)

        return queryset.filter(pk__in=matched_ids)

    def _apply_workorder_payment_aware_date_filter(self, queryset, *, lookup: str, value: date):
        workorder_parent_query = Q(movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT, workorder__isnull=False)
        return queryset.filter(
            (~workorder_parent_query & Q(**{lookup: value}))
            | (
                workorder_parent_query
                & Q(
                    workorder__payments__isnull=False,
                    **{f"workorder__payments__{lookup}": value},
                )
            )
        ).distinct()

    def _apply_report_filters(self, queryset):
        filter_params = self._get_filter_params()
        start_date = filter_params["start_date"]
        end_date = filter_params["end_date"]
        budget_plan_ids = filter_params["budget_plan_ids"]
        bank_account_id = filter_params["bank_account_id"]
        direction = filter_params["direction"]
        paid_status = filter_params["paid_status"]
        agent = filter_params["agent"]
        opened_by_id = filter_params["opened_by_id"]
        payment_method_id = filter_params["payment_method_id"]

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
        start_date = filter_params["start_date"]
        end_date = filter_params["end_date"]
        payment_method_id = filter_params["payment_method_id"]
        paid_status = filter_params["paid_status"]

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
            filtered_payments.append(payment)

        return filtered_payments

    def _build_workorder_payment_row(self, *, movement: FinancialMovement, payment: object) -> dict[str, object]:
        workorder = movement.workorder
        payment_method = getattr(payment, "payment_method", None)
        payment_amount = getattr(payment, "total_paid", None)
        resolved_amount = self._resolve_money_amount(payment_amount)
        workorder_url = reverse("workorder:workorder_detail", kwargs={"pk": movement.workorder_id}) if movement.workorder_id else None

        return {
            "component": f"workorder-payment-{payment.pk}",
            "is_expandable": False,
            "paid_status": self._resolve_workorder_conciliation_status(is_paid=bool(movement.is_paid)),
            "type_badge": movement.report_direction_badge,
            "due_date": payment.due_date,
            "agent": movement.report_agent_display,
            "origin": f"OS #{workorder.pk}" if workorder is not None else "-",
            "description": self._resolve_workorder_description(workorder) if workorder is not None else movement.report_description_display,
            "budget_plan": movement.report_budget_plan_display,
            "account": movement.report_bank_account_display,
            "payment_type": getattr(payment_method, "description", "-") or "-",
            "edit_url": reverse("finance:financial_movement_update", kwargs={"pk": movement.pk}),
            "edit_modal_url": reverse("finance:report_movement_edit", kwargs={"pk": movement.pk}),
            "is_workorder": True,
            "is_group_parent": False,
            "total": {
                "text": f"+ {format_money(payment_amount)}",
                "class": "text-success font-semibold whitespace-nowrap",
            },
            "details": [],
            "summary_direction": FinancialMovement.MovementDirection.CREDIT,
            "summary_amount": resolved_amount,
            "summary_is_paid": True,
            "workorder_url": workorder_url,
        }

    def _get_financial_groups_queryset(self):
        return FinancialGroup.objects.filter(workshop=self.workshop).order_by("sort_key", "id")

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
                {"label": "Créditos Totais", "value": format_money(total_credits), "small": False, "tone": "credit"},
                {"label": "Créditos Pagos", "value": format_money(paid_credits), "small": True, "tone": "credit"},
                {"label": "Débitos Totais", "value": format_money(total_debits), "small": False, "tone": "debit"},
                {"label": "Débitos Pagos", "value": format_money(paid_debits), "small": True, "tone": "debit"},
            ],
            "results": [
                {"label": "Resultado Total", "value": format_money(total_result), "accent": True, "tone": self._resolve_result_tone(total_result)},
                {"label": "Resultado Confirmado", "value": format_money(confirmed_result), "accent": False, "tone": self._resolve_result_tone(confirmed_result)},
            ],
        }

    def _build_selection_summary_card(self, *, rows: list[dict[str, object]]) -> dict[str, object]:
        title = "Créditos e Débitos da Filtragem"
        if not self._has_active_filters():
            return {
                "title": title,
                "is_placeholder": True,
                "description": "Nenhum filtro ou busca ativo",
                "rows": [],
                "results": [],
            }

        return self._build_summary_card_from_rows(title=title, rows=rows)

    def _build_collaborator_payroll_summary_card(self) -> dict[str, object]:
        reference_date = timezone.localdate()
        payrolls = CollaboratorPayroll.objects.filter(workshop=self.workshop, reference_year=reference_date.year, reference_month=reference_date.month).select_related("financial_movement")
        commissions = CollaboratorCommissionEntry.objects.filter(workshop=self.workshop, reference_year=reference_date.year, reference_month=reference_date.month)

        total_forecast = sum((self._resolve_money_amount(payroll.total_amount) for payroll in payrolls), start=Decimal("0.00"))
        total_paid = sum((self._resolve_money_amount(payroll.total_amount) for payroll in payrolls if payroll.financial_movement and payroll.financial_movement.is_paid), start=Decimal("0.00"))
        commissions_forecast = sum((self._resolve_money_amount(entry.commission_amount) for entry in commissions), start=Decimal("0.00"))
        commissions_paid = sum((self._resolve_money_amount(entry.commission_amount) for entry in commissions if entry.status == CollaboratorCommissionEntry.Status.PAID), start=Decimal("0.00"))

        return {
            "title": "Folha e Comissões do Mês",
            "is_placeholder": False,
            "rows": [
                {"label": "Folhas previstas", "value": str(payrolls.count()), "small": False, "tone": "neutral"},
                {"label": "Folhas pagas", "value": str(sum(1 for payroll in payrolls if payroll.financial_movement and payroll.financial_movement.is_paid)), "small": True, "tone": "neutral"},
                {"label": "Comissões previstas", "value": format_money(commissions_forecast), "small": False, "tone": "debit"},
                {"label": "Comissões pagas", "value": format_money(commissions_paid), "small": True, "tone": "debit"},
            ],
            "results": [
                {"label": "Total previsto", "value": format_money(total_forecast), "accent": True, "tone": "debit"},
                {"label": "Total pago", "value": format_money(total_paid), "accent": False, "tone": "debit"},
            ],
        }

    def _build_collaborator_payroll_rows(self) -> list[dict[str, object]]:
        reference_date = timezone.localdate()
        payrolls = CollaboratorPayroll.objects.filter(workshop=self.workshop, reference_year=reference_date.year, reference_month=reference_date.month).select_related("collaborator", "financial_movement").order_by("collaborator__name", "id")
        rows: list[dict[str, object]] = []
        for payroll in payrolls:
            rows.append(
                {
                    "collaborator_name": payroll.collaborator.name,
                    "due_date": payroll.due_date,
                    "salary_amount": payroll.salary_amount,
                    "transport_allowance_amount": payroll.transport_allowance_amount,
                    "benefits_amount": payroll.benefits_amount,
                    "commission_amount": payroll.commission_amount,
                    "total_amount": payroll.total_amount,
                    "paid_amount": payroll.paid_amount,
                    "status": payroll.status,
                    "status_label": payroll.status_label,
                    "history_url": f"{reverse('collaborators:collaborator_update', kwargs={'pk': payroll.collaborator.pk})}?tab=historico&history_month={payroll.reference_month}&history_year={payroll.reference_year}",
                    "receipt_url": reverse("collaborators:collaborator_payroll_receipt", kwargs={"pk": payroll.collaborator.pk, "payroll_id": payroll.pk}),
                }
            )
        return rows

    def _build_financial_movement_row(self, movement: FinancialMovement) -> dict[str, object]:
        workorder = getattr(movement, "workorder", None)
        payment_manager = getattr(workorder, "payments", None)
        payments = list(payment_manager.all()) if payment_manager is not None else []
        latest_payment_date = max((payment.due_date for payment in payments if payment.due_date), default=None)
        paid_status = self._resolve_movement_paid_status_display(movement)
        agent = movement.report_agent_display
        due_date = movement.due_date
        description = movement.report_description_display
        payment_type = movement.report_payment_method_display
        details = []
        edit_modal_url = reverse("finance:report_movement_edit", kwargs={"pk": movement.pk})
        is_workorder = False
        is_group_parent = False
        workorder_url = reverse("workorder:workorder_detail", kwargs={"pk": movement.workorder_id}) if movement.workorder_id else None

        if movement.workorder_id:
            is_workorder = True

        if workorder is not None and movement.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT:
            paid_status = self._resolve_workorder_conciliation_status(is_paid=bool(movement.is_paid))
            due_date = latest_payment_date
            description = self._resolve_workorder_description(workorder)
            payment_type = self._resolve_payment_method_summary(payments)
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
            "type_badge": movement.report_direction_badge,
            "due_date": due_date,
            "agent": agent,
            "origin": movement.report_origin_display if not movement.workorder_id else f"OS #{movement.workorder_id}",
            "description": description,
            "budget_plan": movement.report_budget_plan_display,
            "account": movement.report_bank_account_display,
            "payment_type": payment_type,
            "edit_url": reverse("finance:financial_movement_update", kwargs={"pk": movement.pk}),
            "edit_modal_url": edit_modal_url,
            "is_workorder": is_workorder,
            "is_group_parent": is_group_parent,
            "total": movement.report_total_display,
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

    def _get_financial_movements_page(self, *, rows: list[dict[str, object]]) -> tuple[Any, Paginator]:
        page_number = self.request.GET.get("page") or "1"

        if self._has_active_filters():
            paginator = Paginator(rows, max(len(rows), 1))
            return paginator.get_page(1), paginator

        paginator = Paginator(rows, self.MOVEMENTS_PER_PAGE)
        page_obj = paginator.get_page(page_number)
        return page_obj, paginator

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

    def _get_financial_movement_report_rows(self, *, movements: Any) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        filter_params = self._get_filter_params()
        for movement in movements:
            workorder = getattr(movement, "workorder", None)
            if workorder is not None and movement.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT:
                payments = list(workorder.payments.all())
                payment_rows = [self._build_workorder_payment_row(movement=movement, payment=payment) for payment in self._filter_workorder_payments_for_rows(payments=payments, filter_params=filter_params)]
                rows.extend(payment_rows)
                continue
            rows.append(self._build_financial_movement_row(movement))
        return rows

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        reference_date = timezone.localdate()
        monthly_overview = build_monthly_financial_overview(workshop=self.workshop, reference_date=reference_date)
        yearly_overview = build_yearly_financial_overview(workshop=self.workshop, reference_date=reference_date)
        filter_params = self._get_filter_params()
        all_report_rows = self._get_financial_movement_report_rows(movements=self._get_financial_movements_queryset())
        page_obj, paginator = self._get_financial_movements_page(rows=all_report_rows)

        context["top_summary_cards"] = [
            self._build_summary_card(title="Créditos e Débitos deste Mês", overview=monthly_overview),
            self._build_summary_card(title=f"Balanço Geral {reference_date.year}", overview=yearly_overview),
            self._build_collaborator_payroll_summary_card(),
        ]
        context["selection_summary"] = self._build_selection_summary_card(rows=all_report_rows)
        context["financial_movement_report_rows"] = page_obj.object_list
        context["collaborator_payroll_rows"] = self._build_collaborator_payroll_rows()
        context["financial_group_filters"] = self._get_financial_groups_queryset()
        context["bank_account_filters"] = self._get_bank_accounts_queryset()
        context["direction_filter_choices"] = self.FILTER_DIRECTION_CHOICES
        context["paid_status_filter_choices"] = self.FILTER_PAID_STATUS_CHOICES
        context["selected_financial_group_ids"] = set(filter_params["budget_plan_ids"])
        context["selected_bank_account_id"] = filter_params["bank_account_id"]
        context["selected_direction"] = filter_params["direction"]
        context["selected_paid_status"] = filter_params["paid_status"]

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
        self.object.delete()
        if self.request.htmx:
            response = HttpResponse()
            response["HX-Refresh"] = "true"
            return response
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse("finance:reports_home")
