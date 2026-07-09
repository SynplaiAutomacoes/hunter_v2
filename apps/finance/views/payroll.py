from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView
from django.http import HttpResponseRedirect

from django.db import transaction

from djmoney.money import Money

from apps.collaborators.models import CollaboratorCommissionEntry, CollaboratorPayroll, WorkshopCollaborator
from apps.collaborators.services import (
    PAYROLL_COMPONENT_LABELS,
    build_payroll_projection,
    calculate_transport_allowance_total,
    ensure_payroll_component_movements_confirmed,
    ensure_payroll_movements_confirmed,
    get_payroll_due_date_for_reference,
    get_payroll_movement_diagnosis,
    mark_payroll_as_paid,
    mark_payroll_as_unpaid,
    mark_payroll_commissions_as_paid,
    payroll_has_financial_movements,
    recalculate_payroll_from_linked_movements,
    refresh_unpaid_payroll_due_dates,
    sync_collaborator_payroll,
    sync_collaborator_payrolls_batch,
    unmark_payroll_commissions_as_paid,
)
from apps.core.presentation.widgets import CalendarDateInput, MoneyInput, SearchableSelectInput, TextInput, TextareaInput
from apps.finance.models.bank_account import BankAccount
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.views.commissions import MONTH_CHOICES, _parse_int_param, build_paid_status_indicator
from apps.workshops.mixin import WorkshopScopedMixin


class PayrollPaymentForm(forms.ModelForm):
    is_paid = forms.TypedChoiceField(
        label="Pago",
        required=True,
        coerce=lambda value: str(value).lower() == "true",
        choices=((False, "Não"), (True, "Sim")),
        widget=SearchableSelectInput(choices=[(False, "Não"), (True, "Sim")]),
    )
    is_reconciled = forms.TypedChoiceField(
        label="Conciliado",
        required=True,
        coerce=lambda value: str(value).lower() == "true",
        choices=((False, "Aguardando Conciliação"), (True, "Conciliado")),
        widget=SearchableSelectInput(choices=[(False, "Aguardando Conciliação"), (True, "Conciliado")]),
        initial=False,
    )

    class Meta:
        model = FinancialMovement
        fields = ["due_date", "amount", "budget_plan", "bank_account", "payment_method", "is_paid", "is_reconciled", "nf_number", "financial_observation"]
        widgets = {
            "due_date": CalendarDateInput(),
            "amount": MoneyInput(),
            "budget_plan": SearchableSelectInput(),
            "bank_account": SearchableSelectInput(),
            "payment_method": SearchableSelectInput(),
            "nf_number": TextInput(),
            "financial_observation": TextareaInput(rows=3),
        }

    def __init__(self, *args: Any, workshop=None, **kwargs: Any) -> None:
        payroll: CollaboratorPayroll | None = kwargs.pop("payroll", None)
        super().__init__(*args, **kwargs)
        self.fields["is_paid"].initial = bool(self.instance.is_paid) if self.instance.pk else False
        self.fields["is_reconciled"].initial = bool(self.instance.is_reconciled) if self.instance.pk else False
        self.fields["budget_plan"].required = False
        self.fields["bank_account"].required = False
        self.fields["payment_method"].required = False
        if payroll is not None:
            self.fields["due_date"].initial = self.instance.due_date or payroll.due_date
            self.fields["amount"].initial = self.instance.amount or payroll.total_amount
        if workshop is not None:
            groups = FinancialGroup.objects.filter(workshop=workshop).order_by("name")
            accounts = BankAccount.objects.filter(workshop=workshop).order_by("bank_name", "account_number", "id")
            methods = PaymentMethod.objects.filter(workshop=workshop, is_active=True).order_by("description")
            self.fields["budget_plan"].queryset = groups
            self.fields["bank_account"].queryset = accounts
            self.fields["payment_method"].queryset = methods
            self.fields["budget_plan"].widget.choices = [(item.pk, str(item)) for item in groups]
            self.fields["bank_account"].widget.choices = [(item.pk, str(item)) for item in accounts]
            self.fields["payment_method"].widget.choices = [(item.pk, str(item)) for item in methods]


class PayrollListView(LoginRequiredMixin, WorkshopScopedMixin, TemplateView):
    model = CollaboratorPayroll
    template_name = "finance/payroll/list.html"
    workshop_permission_app_label = "finance"
    workshop_permission_model = "financialmovement"
    workshop_permission_codename = "view_financialmovement"
    PER_PAGE = 20
    STATUS_CHOICES = (("", "Todos"), (CollaboratorPayroll.Status.FORECAST, "Não Pago"), (CollaboratorPayroll.Status.PAID, "Pago"))

    @staticmethod
    def _parse_date_param(raw_value: str | None) -> date | None:
        value = str(raw_value or "").strip()
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def _get_selected_collaborator_id(self) -> int | None:
        raw_value = str(self.request.GET.get("collaborator") or "").strip()
        if not raw_value:
            return None
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    def _get_filter_params(self) -> dict[str, Any]:
        today = timezone.localdate()
        start_date = self._parse_date_param(self.request.GET.get("data_inicial"))
        end_date = self._parse_date_param(self.request.GET.get("data_final"))
        selected_status = str(self.request.GET.get("status") or "").strip()
        if selected_status not in {CollaboratorPayroll.Status.FORECAST, CollaboratorPayroll.Status.PAID}:
            selected_status = ""
        return {
            "start_date": start_date,
            "end_date": end_date,
            "collaborator_id": self._get_selected_collaborator_id(),
            "status": selected_status,
            "month": _parse_int_param(self.request.GET.get("mes"), default=today.month, minimum=1, maximum=12),
            "year": _parse_int_param(self.request.GET.get("ano"), default=today.year, minimum=2000, maximum=9999),
            "has_modal_date_filter": bool(start_date or end_date),
        }

    def _get_active_collaborators_queryset(self, *, filters: dict[str, Any]):
        if filters["has_modal_date_filter"]:
            return WorkshopCollaborator.objects.none()

        reference_date = date(filters["year"], filters["month"], 1)
        collaborators = WorkshopCollaborator.objects.filter(
            workshop=self.workshop,
            is_active=True,
            admission_date__lte=reference_date,
        ).filter(Q(termination_date__isnull=True) | Q(termination_date__gte=reference_date))

        if filters["collaborator_id"] is not None:
            collaborators = collaborators.filter(pk=filters["collaborator_id"])

        search = str(self.request.GET.get("search") or "").strip()
        if search:
            collaborators = collaborators.filter(name__icontains=search)

        collaborator_ids = list(collaborators.values_list("pk", flat=True))
        if not collaborator_ids:
            return collaborators.none()

        return collaborators

    def _get_collaborators_to_sync(self, *, filters: dict[str, Any]):
        collaborators = self._get_active_collaborators_queryset(filters=filters)
        collaborator_ids = list(collaborators.values_list("pk", flat=True))
        if not collaborator_ids:
            return collaborators.none()

        synced_collaborator_ids = set(
            CollaboratorPayroll.objects.filter(
                workshop=self.workshop,
                collaborator_id__in=collaborator_ids,
                reference_month=filters["month"],
                reference_year=filters["year"],
                financial_movement_id__isnull=False,
            ).values_list("collaborator_id", flat=True)
        )
        return collaborators.exclude(pk__in=synced_collaborator_ids)

    def _sync_monthly_payrolls(self, *, filters: dict[str, Any]) -> None:
        reference_date = date(filters["year"], filters["month"], 1)
        collaborators_to_sync = list(self._get_collaborators_to_sync(filters=filters).order_by("name", "id"))
        sync_collaborator_payrolls_batch(collaborators=collaborators_to_sync, reference_date=reference_date, lock_reference=True)

    def _get_pending_collaborator_rows(self, *, filters: dict[str, Any], existing_collaborator_ids: set[int]) -> list[dict[str, Any]]:
        if filters["has_modal_date_filter"]:
            return []

        reference_date = date(filters["year"], filters["month"], 1)
        rows: list[dict[str, Any]] = []
        for collaborator in self._get_active_collaborators_queryset(filters=filters).order_by("name", "id"):
            if collaborator.pk in existing_collaborator_ids:
                continue

            benefits_amount = sum(
                (Decimal(str(benefit.monthly_amount.amount or 0)) for benefit in collaborator.benefits.filter(is_active=True)),
                start=Decimal("0.00"),
            )
            commission_amount = sum(
                (
                    Decimal(str(entry.commission_amount.amount or 0))
                    for entry in CollaboratorCommissionEntry.objects.filter(
                        collaborator=collaborator,
                        reference_year=filters["year"],
                        reference_month=filters["month"],
                    ).only("commission_amount")
                ),
                start=Decimal("0.00"),
            )
            salary_amount = Decimal(str(collaborator.salary.amount or 0))
            transport_amount = Decimal(str(calculate_transport_allowance_total(collaborator=collaborator, reference_date=reference_date).amount or 0))
            total_amount = salary_amount + transport_amount + benefits_amount + commission_amount
            missing_components: list[str] = []
            if salary_amount > Decimal("0.00"):
                missing_components.append("Salário")
            if transport_amount > Decimal("0.00"):
                missing_components.append("Vale Transporte")
            if benefits_amount > Decimal("0.00"):
                missing_components.append("Benefícios")
            if commission_amount > Decimal("0.00"):
                missing_components.append("Comissões")
            rows.append(
                {
                    "id": None,
                    "collaborator_name": collaborator.name,
                    "due_date": get_payroll_due_date_for_reference(collaborator=collaborator, reference_date=reference_date),
                    "salary_amount": Money(salary_amount, "BRL"),
                    "transport_allowance_amount": Money(transport_amount, "BRL"),
                    "benefits_amount": Money(benefits_amount, "BRL"),
                    "commission_amount": Money(commission_amount, "BRL"),
                    "total_amount": Money(total_amount, "BRL"),
                    "paid_amount": Money(0, "BRL"),
                    "status": "PENDING_CREATION",
                    "status_label": "Pendente de criação",
                    "is_paid": False,
                    "paid_indicator": {"icon": "schedule", "class": "text-warning"},
                    "is_reconciled": False,
                    "reconciliation_label": "Aguardando criação",
                    "reconciliation_indicator": {"icon": "schedule", "class": "text-warning"},
                    "edit_url": f"{reverse('finance:payroll_edit_modal_for_collaborator', kwargs={'collaborator_pk': collaborator.pk})}?mes={filters['month']}&ano={filters['year']}",
                    "receipt_url": "",
                    "is_pending_creation": True,
                    "can_select": False,
                    "missing_components": missing_components,
                }
            )
        return rows

    def _get_queryset(self):
        filters = self._get_filter_params()
        queryset = CollaboratorPayroll.objects.filter(workshop=self.workshop).select_related("collaborator", "financial_movement").order_by("collaborator__name", "id")
        if filters["has_modal_date_filter"]:
            if filters["start_date"]:
                queryset = queryset.filter(due_date__gte=filters["start_date"])
            if filters["end_date"]:
                queryset = queryset.filter(due_date__lte=filters["end_date"])
        else:
            queryset = queryset.filter(reference_month=filters["month"], reference_year=filters["year"])
        if filters["collaborator_id"] is not None:
            queryset = queryset.filter(collaborator_id=filters["collaborator_id"])
        if filters["status"] == CollaboratorPayroll.Status.PAID:
            queryset = queryset.filter(financial_movement__is_paid=True)
        elif filters["status"] == CollaboratorPayroll.Status.FORECAST:
            queryset = queryset.exclude(financial_movement__is_paid=True)
        search = str(self.request.GET.get("search") or "").strip()
        if search:
            queryset = queryset.filter(collaborator__name__icontains=search)
        return queryset

    @staticmethod
    def _money_amount(value: object) -> Decimal:
        return Decimal(str(getattr(value, "amount", value) or 0))

    def _build_rows(self, payrolls: list[CollaboratorPayroll]) -> list[dict[str, Any]]:
        rows = []
        for payroll in payrolls:
            is_reconciled = bool(payroll.financial_movement and payroll.financial_movement.is_reconciled)
            diagnosis = get_payroll_movement_diagnosis(payroll=payroll)
            rows.append(
                {
                    "id": payroll.pk,
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
                    "is_paid": payroll.status == CollaboratorPayroll.Status.PAID,
                    "paid_indicator": build_paid_status_indicator(is_paid=payroll.status == CollaboratorPayroll.Status.PAID),
                    "is_reconciled": is_reconciled,
                    "reconciliation_label": "Conciliado" if is_reconciled else "Aguardando Conciliação",
                    "reconciliation_indicator": {
                        "icon": "check_circle" if is_reconciled else "schedule",
                        "class": "text-success" if is_reconciled else "text-warning",
                    },
                    "edit_url": reverse("finance:payroll_edit_modal", kwargs={"pk": payroll.pk}),
                    "receipt_url": reverse("collaborators:collaborator_payroll_receipt", kwargs={"pk": payroll.collaborator.pk, "payroll_id": payroll.pk}),
                    "is_pending_creation": False,
                    "can_select": True,
                    "missing_components": diagnosis.missing_components,
                }
            )
        return rows

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        filters = self._get_filter_params()
        queryset = self._get_queryset()
        paginator = Paginator(queryset, self.PER_PAGE)
        page_obj = paginator.get_page(self.request.GET.get("page") or "1")
        payrolls = list(page_obj.object_list)
        existing_rows = self._build_rows(payrolls)
        pending_rows = self._get_pending_collaborator_rows(filters=filters, existing_collaborator_ids={payroll.collaborator.pk for payroll in queryset})
        context["payroll_rows"] = existing_rows + pending_rows
        totals = queryset.aggregate(total_payroll_amount=Sum("total_amount"), paid_amount=Sum("total_amount", filter=Q(financial_movement__is_paid=True)))
        total_amount = self._money_amount(totals.get("total_payroll_amount"))
        paid_amount = self._money_amount(totals.get("paid_amount"))
        context["pending_amount"] = max(total_amount - paid_amount, Decimal("0.00"))
        context["paid_amount"] = paid_amount
        context["collaborator_filters"] = WorkshopCollaborator.objects.filter(workshop=self.workshop, is_active=True).order_by("name")
        context["status_choices"] = self.STATUS_CHOICES
        context["selected_collaborator_id"] = filters["collaborator_id"]
        context["selected_status"] = filters["status"]
        context["selected_month"] = filters["month"]
        context["selected_year"] = filters["year"]
        context["month_choices"] = MONTH_CHOICES
        context["year_choices"] = range(timezone.localdate().year - 4, timezone.localdate().year + 2)
        context["has_modal_date_filter"] = filters["has_modal_date_filter"]
        context["can_refresh_payroll"] = not filters["has_modal_date_filter"]
        context["clear_filters_url"] = reverse("finance:payroll_list")
        context["has_active_filters"] = bool(filters["start_date"] or filters["end_date"] or filters["collaborator_id"] is not None or filters["status"] or self.request.GET.get("search") or self.request.GET.get("mes") or self.request.GET.get("ano"))
        context["page_obj"] = page_obj
        context["is_paginated"] = paginator.num_pages > 1
        return context


class PayrollRefreshView(PayrollListView, View):
    workshop_permission_codename = "change_financialmovement"

    def post(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        filters = self._get_filter_params()
        collaborators_to_sync = list(self._get_collaborators_to_sync(filters=filters).order_by("name", "id"))

        if request.headers.get("HX-Request") and request.POST.get("confirm_create") != "true":
            return render(
                request,
                "finance/payroll/partials/refresh_confirm_modal.html",
                {
                    "collaborators": collaborators_to_sync,
                    "filters": filters,
                },
            )

        if request.POST.get("confirm_create") == "true":
            self._sync_monthly_payrolls(filters=filters)
            refresh_unpaid_payroll_due_dates(workshop=self.workshop, reference_year=filters["year"], reference_month=filters["month"])
            if request.headers.get("HX-Request"):
                return _build_hx_toast_response(message="Folhas criadas/atualizadas com sucesso.", toast_type="success", refresh=True)

        params = QueryDict("", mutable=True)
        for key in ["search", "mes", "ano", "data_inicial", "data_final", "collaborator", "status", "page"]:
            value = request.POST.get(key)
            if value not in (None, ""):
                params[key] = value

        redirect_url = reverse("finance:payroll_list")
        querystring = params.urlencode()
        if querystring:
            redirect_url = f"{redirect_url}?{querystring}"
        return HttpResponseRedirect(redirect_url)


def _get_payroll_reference_date(*, payroll: CollaboratorPayroll) -> date:
    return date(payroll.reference_year, payroll.reference_month, 1)


def _mark_payroll_commissions_as_paid(*, payroll: CollaboratorPayroll) -> None:
    mark_payroll_commissions_as_paid(payroll=payroll, paid_at=timezone.localdate())


def _unmark_payroll_commissions_as_paid(*, payroll: CollaboratorPayroll) -> None:
    unmark_payroll_commissions_as_paid(payroll=payroll)


def _mark_payroll_as_paid(*, payroll: CollaboratorPayroll) -> CollaboratorPayroll:
    return mark_payroll_as_paid(payroll=payroll, paid_at=timezone.localdate())


def _mark_payroll_as_unpaid(*, payroll: CollaboratorPayroll) -> CollaboratorPayroll:
    return mark_payroll_as_unpaid(payroll=payroll)


def _payroll_missing_movement_message(*, collaborator_names: list[str], action_label: str) -> str:
    skipped_count = len(collaborator_names)
    base_message = f"{skipped_count} folha{'s' if skipped_count != 1 else ''} foram ignorada{'s' if skipped_count != 1 else ''} ao {action_label} porque nao possuem movimentacoes financeiras."
    if not collaborator_names:
        return base_message
    return f"{base_message} Colaboradores: {', '.join(collaborator_names)}"


def _build_hx_toast_response(*, message: str, toast_type: str, refresh: bool = False, status: int = 200) -> HttpResponse:
    response = HttpResponse(status=status)
    if refresh:
        response["HX-Refresh"] = "true"
    response["HX-Trigger"] = json.dumps({"showToast": {"message": message, "type": toast_type}})
    return response


class PayrollEditModalView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = CollaboratorPayroll
    workshop_permission_app_label = "finance"
    workshop_permission_model = "financialmovement"
    workshop_permission_codename = "change_financialmovement"
    template_name = "finance/payroll/partials/edit_modal.html"

    def _get_reference_date(self) -> date:
        month = _parse_int_param(self.request.GET.get("mes") or self.request.POST.get("mes"), default=timezone.localdate().month, minimum=1, maximum=12)
        year = _parse_int_param(self.request.GET.get("ano") or self.request.POST.get("ano"), default=timezone.localdate().year, minimum=2000, maximum=9999)
        return date(year, month, 1)

    def _get_collaborator(self) -> WorkshopCollaborator:
        if "collaborator_pk" in self.kwargs:
            return get_object_or_404(WorkshopCollaborator, pk=self.kwargs["collaborator_pk"], workshop=self.workshop)
        return self._get_payroll().collaborator

    def _get_payroll(self) -> CollaboratorPayroll:
        return get_object_or_404(
            CollaboratorPayroll.objects.select_related("collaborator", "financial_movement").prefetch_related("items", "commission_entries__workorder__budget"),
            pk=self.kwargs["pk"],
            workshop=self.workshop,
        )

    def _get_existing_payroll(self) -> CollaboratorPayroll | None:
        if "pk" in self.kwargs:
            return self._get_payroll()
        collaborator = self._get_collaborator()
        reference_date = self._get_reference_date()
        return (
            CollaboratorPayroll.objects.select_related("collaborator", "financial_movement")
            .prefetch_related("items", "commission_entries__workorder__budget")
            .filter(
                workshop=self.workshop,
                collaborator=collaborator,
                reference_month=reference_date.month,
                reference_year=reference_date.year,
            )
            .first()
        )

    def _get_modal_url(self, *, collaborator: WorkshopCollaborator | None = None, payroll: CollaboratorPayroll | None = None) -> str:
        if payroll is not None:
            return reverse("finance:payroll_edit_modal", kwargs={"pk": payroll.pk})
        assert collaborator is not None
        return reverse("finance:payroll_edit_modal_for_collaborator", kwargs={"collaborator_pk": collaborator.pk})

    @staticmethod
    def _resolve_preview_components(*, payroll: CollaboratorPayroll) -> list[str]:
        components: list[str] = []
        component_amounts = [
            (FinancialMovement.PayrollComponent.SALARY, payroll.salary_amount),
            (FinancialMovement.PayrollComponent.TRANSPORT, payroll.transport_allowance_amount),
            (FinancialMovement.PayrollComponent.BENEFIT, payroll.benefits_amount),
            (FinancialMovement.PayrollComponent.COMMISSION, payroll.commission_amount),
        ]
        for component, amount in component_amounts:
            if Decimal(str(amount.amount or 0)) > 0:
                components.append(PAYROLL_COMPONENT_LABELS[component])
        return components

    @staticmethod
    def _get_financial_tab_order() -> list[str]:
        return [
            FinancialMovement.PayrollComponent.SALARY,
            FinancialMovement.PayrollComponent.TRANSPORT,
            FinancialMovement.PayrollComponent.BENEFIT,
            FinancialMovement.PayrollComponent.COMMISSION,
        ]

    def _get_requested_tab(self) -> str:
        return str(self.request.GET.get("tab") or self.request.POST.get("tab") or FinancialMovement.PayrollComponent.SALARY)

    def _get_requested_movement_id(self) -> int | None:
        raw_value = self.request.GET.get("movement_id") or self.request.POST.get("movement_id")
        try:
            return int(str(raw_value)) if raw_value else None
        except (TypeError, ValueError):
            return None

    def _build_component_tabs(self, *, payroll: CollaboratorPayroll) -> list[dict[str, Any]]:
        projection = build_payroll_projection(collaborator=payroll.collaborator, reference_date=date(payroll.reference_year, payroll.reference_month, 1))
        component_amounts = {
            str(FinancialMovement.PayrollComponent.SALARY): projection.salary_amount,
            str(FinancialMovement.PayrollComponent.TRANSPORT): projection.transport_allowance_amount,
            str(FinancialMovement.PayrollComponent.BENEFIT): projection.benefits_amount,
            str(FinancialMovement.PayrollComponent.COMMISSION): projection.commission_amount,
        }
        grouped_movements: dict[str, list[FinancialMovement]] = {component: [] for component in self._get_financial_tab_order()}
        for movement in payroll.get_financial_movements():
            component_key = str(movement.payroll_component or FinancialMovement.PayrollComponent.SALARY)
            if component_key in grouped_movements:
                grouped_movements[component_key].append(movement)

        tabs: list[dict[str, Any]] = []
        for component in self._get_financial_tab_order():
            amount = component_amounts.get(component)
            expected = Decimal(str(amount.amount or 0)) > 0 if amount is not None else False
            movements = grouped_movements.get(component, [])
            tabs.append(
                {
                    "key": component,
                    "label": PAYROLL_COMPONENT_LABELS.get(component, component),
                    "movements": movements,
                    "has_expected_value": expected,
                    "is_missing": expected and not movements,
                }
            )
        return tabs

    @staticmethod
    def _get_first_available_financial_tab(component_tabs: list[dict[str, Any]]) -> str:
        for tab in component_tabs:
            if tab["movements"]:
                return str(tab["key"])
        return "summary"

    def _build_component_url(self, *, payroll: CollaboratorPayroll, tab: str, movement_id: int | None = None, continue_without_create: bool = False, prompt_create_component: str | None = None) -> str:
        params = QueryDict("", mutable=True)
        params["tab"] = tab
        if movement_id is not None:
            params["movement_id"] = str(movement_id)
        if continue_without_create:
            params["continue_without_create"] = "true"
        if prompt_create_component:
            params["prompt_create_component"] = prompt_create_component
        query = params.urlencode()
        return f"{self._get_modal_url(payroll=payroll)}?{query}" if query else self._get_modal_url(payroll=payroll)

    def _build_confirmation_response(self, *, request: Any, collaborator: WorkshopCollaborator, payroll: CollaboratorPayroll | None, component_to_create: str | None = None, continue_url: str | None = None) -> HttpResponse:
        reference_date = self._get_reference_date()
        preview_payroll = payroll or build_payroll_projection(collaborator=collaborator, reference_date=reference_date)
        if component_to_create is not None:
            missing_components = [PAYROLL_COMPONENT_LABELS.get(component_to_create, component_to_create)]
        else:
            missing_components = self._resolve_preview_components(payroll=preview_payroll) if payroll is None else get_payroll_movement_diagnosis(payroll=preview_payroll).missing_components

        return render(
            request,
            "finance/payroll/partials/confirm_create_modal.html",
            {
                "payroll": preview_payroll,
                "collaborator": collaborator,
                "missing_components": missing_components,
                "reference_date": reference_date,
                "post_url": request.path,
                "source_filters": {"mes": reference_date.month, "ano": reference_date.year},
                "is_new_payroll": payroll is None,
                "continue_url": continue_url,
                "component_to_create": component_to_create,
            },
        )

    def _open_edit_modal(self, *, request: Any, payroll: CollaboratorPayroll) -> HttpResponse:
        component_tabs = self._build_component_tabs(payroll=payroll)
        selected_tab = self._get_requested_tab()
        fallback_tab = self._get_first_available_financial_tab(component_tabs)

        if selected_tab not in {"collaborator", "commissions_history", "summary"}:
            active_component_tab = next((tab for tab in component_tabs if tab["key"] == selected_tab), None)
            if active_component_tab is None or active_component_tab["is_missing"]:
                selected_tab = fallback_tab

        modal_url = self._get_modal_url(payroll=payroll)

        default_movement_ids: dict[str, int | None] = {}
        for tab in component_tabs:
            default_movement_ids[tab["key"]] = tab["movements"][0].pk if tab["movements"] else None

        requested_movement_id = self._get_requested_movement_id()
        if requested_movement_id is not None and selected_tab not in {"collaborator", "commissions_history", "summary"}:
            active_tab = next((tab for tab in component_tabs if tab["key"] == selected_tab), None)
            if active_tab is not None:
                matching = [m for m in active_tab["movements"] if m.pk == requested_movement_id]
                if matching:
                    default_movement_ids[selected_tab] = matching[0].pk

        for tab in component_tabs:
            movement_id = default_movement_ids.get(tab["key"])
            movement = next((m for m in tab["movements"] if m.pk == movement_id), None) if movement_id is not None else None
            tab["default_movement_id"] = movement_id
            tab["form"] = PayrollPaymentForm(instance=movement, workshop=self.workshop, payroll=payroll) if movement is not None else None

        return render(
            request,
            self.template_name,
            {
                "payroll": payroll,
                "selected_tab": selected_tab,
                "component_tabs": component_tabs,
                "modal_url": modal_url,
                "fallback_tab": fallback_tab,
                "continue_without_create": True,
            },
        )

    def get(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        payroll = self._get_existing_payroll()
        collaborator = self._get_collaborator()
        if payroll is None:
            return self._build_confirmation_response(request=request, collaborator=collaborator, payroll=None)

        if request.GET.get("prompt_create_component"):
            component_to_create = str(request.GET["prompt_create_component"])
            component_tabs = self._build_component_tabs(payroll=payroll)
            continue_url = self._build_component_url(payroll=payroll, tab=self._get_first_available_financial_tab(component_tabs), continue_without_create=True)
            return self._build_confirmation_response(request=request, collaborator=collaborator, payroll=payroll, component_to_create=component_to_create, continue_url=continue_url)

        diagnosis = get_payroll_movement_diagnosis(payroll=payroll)
        has_movements = payroll_has_financial_movements(payroll=payroll)
        if not has_movements:
            return self._build_confirmation_response(request=request, collaborator=collaborator, payroll=payroll)
        if diagnosis.requires_confirmation and request.GET.get("continue_without_create") != "true":
            component_tabs = self._build_component_tabs(payroll=payroll)
            continue_url = self._build_component_url(payroll=payroll, tab=self._get_first_available_financial_tab(component_tabs), continue_without_create=True)
            return self._build_confirmation_response(request=request, collaborator=collaborator, payroll=payroll, continue_url=continue_url)

        return self._open_edit_modal(request=request, payroll=payroll)

    def post(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        payroll = self._get_existing_payroll()
        collaborator = self._get_collaborator()
        reference_date = self._get_reference_date()

        if request.POST.get("confirm_create") == "true":
            target_payroll = payroll
            if target_payroll is None:
                target_payroll = sync_collaborator_payroll(collaborator=collaborator, reference_date=reference_date, lock_reference=True)
            elif request.POST.get("component_to_create"):
                target_payroll = ensure_payroll_component_movements_confirmed(payroll=target_payroll, component=str(request.POST["component_to_create"]))
            else:
                target_payroll = ensure_payroll_movements_confirmed(payroll=target_payroll)

            if not payroll_has_financial_movements(payroll=target_payroll) or target_payroll.financial_movement is None:
                return _build_hx_toast_response(
                    message="Nao foi possivel gerar movimentacoes financeiras para esta folha.",
                    toast_type="warning",
                    refresh=True,
                    status=400,
                )
            return self._open_edit_modal(request=request, payroll=target_payroll)

        if payroll is None or not payroll_has_financial_movements(payroll=payroll) or payroll.financial_movement is None:
            return self._build_confirmation_response(request=request, collaborator=collaborator, payroll=payroll)

        component_tabs = self._build_component_tabs(payroll=payroll)
        active_component_tab = next((tab for tab in component_tabs if tab["key"] == self._get_requested_tab()), None)
        movement_id = self._get_requested_movement_id()
        selected_movement = None
        if active_component_tab is not None:
            selected_movement = next((movement for movement in active_component_tab["movements"] if movement_id is not None and movement.pk == movement_id), None)
            if selected_movement is None and active_component_tab["movements"]:
                selected_movement = active_component_tab["movements"][0]
        if selected_movement is None:
            return self._open_edit_modal(request=request, payroll=payroll)

        form = PayrollPaymentForm(request.POST, instance=selected_movement, workshop=self.workshop, payroll=payroll)
        if form.is_valid():
            due_date = form.cleaned_data["due_date"]
            if payroll.due_date != due_date:
                payroll.due_date = due_date
                payroll.save(update_fields=["due_date"])
            movement = form.save()
            recalculate_payroll_from_linked_movements(payroll=payroll)
            if movement.is_paid:
                _mark_payroll_as_paid(payroll=payroll)
            else:
                _mark_payroll_as_unpaid(payroll=payroll)
                _unmark_payroll_commissions_as_paid(payroll=payroll)
            response = HttpResponse()
            response["HX-Refresh"] = "true"
            response["HX-Trigger"] = '{"showToast": {"message": "Folha atualizada com sucesso.", "type": "success"}}'
            return response
        response = render(request, self.template_name, {"payroll": payroll, "form": form}, status=400)
        response["HX-Trigger"] = '{"showToast": {"message": "Revise os dados da folha.", "type": "error"}}'
        return response


class PayrollBulkPayView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "financialmovement"
    workshop_permission_codename = "change_financialmovement"

    def post(self, request, *args, **kwargs):
        raw_values = request.POST.getlist("payroll_ids")
        if not raw_values:
            return HttpResponse("Nenhuma folha selecionada.", status=400)

        payroll_ids = []
        for value in raw_values:
            try:
                payroll_ids.append(int(value))
            except (TypeError, ValueError):
                pass

        if not payroll_ids:
            return HttpResponse("Nenhuma folha selecionada.", status=400)

        payrolls = CollaboratorPayroll.objects.filter(
            pk__in=payroll_ids,
            workshop=self.workshop,
        ).select_related("collaborator", "financial_movement")

        skipped_collaborators: list[str] = []
        with transaction.atomic():
            for payroll in payrolls:
                if not payroll_has_financial_movements(payroll=payroll):
                    skipped_collaborators.append(payroll.collaborator.name)
                    continue
                refreshed_payroll = _mark_payroll_as_paid(payroll=payroll)
                if not payroll_has_financial_movements(payroll=refreshed_payroll):
                    skipped_collaborators.append(refreshed_payroll.collaborator.name)

        if request.headers.get("HX-Request"):
            if skipped_collaborators:
                return _build_hx_toast_response(
                    message=_payroll_missing_movement_message(collaborator_names=skipped_collaborators, action_label="marcar como pagas"),
                    toast_type="warning",
                    refresh=True,
                )
            response = HttpResponse()
            response["HX-Refresh"] = "true"
            return response

        if skipped_collaborators:
            messages.warning(request, _payroll_missing_movement_message(collaborator_names=skipped_collaborators, action_label="marcar como pagas"))

        return HttpResponseRedirect(reverse("finance:payroll_list"))


class PayrollBulkUnpayView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "financialmovement"
    workshop_permission_codename = "change_financialmovement"

    def post(self, request, *args, **kwargs):
        raw_values = request.POST.getlist("payroll_ids")
        if not raw_values:
            return HttpResponse("Nenhuma folha selecionada.", status=400)

        payroll_ids = []
        for value in raw_values:
            try:
                payroll_ids.append(int(value))
            except (TypeError, ValueError):
                pass

        if not payroll_ids:
            return HttpResponse("Nenhuma folha selecionada.", status=400)

        payrolls = CollaboratorPayroll.objects.filter(
            pk__in=payroll_ids,
            workshop=self.workshop,
        ).select_related("collaborator", "financial_movement")

        with transaction.atomic():
            for payroll in payrolls:
                _mark_payroll_as_unpaid(payroll=payroll)
                _unmark_payroll_commissions_as_paid(payroll=payroll)

        if request.headers.get("HX-Request"):
            response = HttpResponse()
            response["HX-Refresh"] = "true"
            return response

        return HttpResponseRedirect(reverse("finance:payroll_list"))
