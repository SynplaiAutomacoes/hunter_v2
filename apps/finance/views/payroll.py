from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django import forms
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView
from django.http import HttpResponseRedirect

from django.db import transaction

from apps.collaborators.models import CollaboratorPayroll, WorkshopCollaborator
from apps.collaborators.services import ensure_payroll_financial_movement, mark_payroll_as_paid, mark_payroll_commissions_as_paid, sync_collaborator_payroll, unmark_payroll_commissions_as_paid
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

    def _sync_monthly_payrolls(self, *, filters: dict[str, Any]) -> None:
        if filters["has_modal_date_filter"]:
            return

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

        for collaborator in collaborators.order_by("name", "id").iterator():
            sync_collaborator_payroll(collaborator=collaborator, reference_date=reference_date, lock_reference=True)

    def _get_queryset(self):
        filters = self._get_filter_params()
        self._sync_monthly_payrolls(filters=filters)
        queryset = CollaboratorPayroll.objects.filter(workshop=self.workshop).select_related("collaborator", "financial_movement").prefetch_related("items", "commission_entries__workorder").order_by("collaborator__name", "id")
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
                    "receipt_url": reverse("collaborators:collaborator_payroll_receipt", kwargs={"pk": payroll.collaborator_id, "payroll_id": payroll.pk}),
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
        context["payroll_rows"] = self._build_rows(payrolls)
        total_amount = sum((self._money_amount(payroll.total_amount) for payroll in queryset), start=Decimal("0.00"))
        paid_amount = sum((self._money_amount(payroll.paid_amount) for payroll in queryset), start=Decimal("0.00"))
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
        context["clear_filters_url"] = reverse("finance:payroll_list")
        context["has_active_filters"] = bool(filters["start_date"] or filters["end_date"] or filters["collaborator_id"] is not None or filters["status"] or self.request.GET.get("search") or self.request.GET.get("mes") or self.request.GET.get("ano"))
        context["page_obj"] = page_obj
        context["is_paginated"] = paginator.num_pages > 1
        return context


def _get_payroll_reference_date(*, payroll: CollaboratorPayroll) -> date:
    return date(payroll.reference_year, payroll.reference_month, 1)


def _mark_payroll_commissions_as_paid(*, payroll: CollaboratorPayroll) -> None:
    mark_payroll_commissions_as_paid(payroll=payroll, paid_at=timezone.localdate())


def _unmark_payroll_commissions_as_paid(*, payroll: CollaboratorPayroll) -> None:
    unmark_payroll_commissions_as_paid(payroll=payroll)


def _ensure_payroll_financial_movement(*, payroll: CollaboratorPayroll) -> CollaboratorPayroll:
    return ensure_payroll_financial_movement(payroll=payroll)


def _mark_payroll_as_paid(*, payroll: CollaboratorPayroll) -> CollaboratorPayroll:
    return mark_payroll_as_paid(payroll=payroll, paid_at=timezone.localdate())


class PayrollEditModalView(LoginRequiredMixin, WorkshopScopedMixin, View):
    model = CollaboratorPayroll
    workshop_permission_app_label = "finance"
    workshop_permission_model = "financialmovement"
    workshop_permission_codename = "change_financialmovement"
    template_name = "finance/payroll/partials/edit_modal.html"

    def _get_payroll(self) -> CollaboratorPayroll:
        return get_object_or_404(
            CollaboratorPayroll.objects.select_related("collaborator", "financial_movement").prefetch_related("items", "commission_entries__workorder"),
            pk=self.kwargs["pk"],
            workshop=self.workshop,
        )

    def get(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        payroll = self._get_payroll()
        if payroll.financial_movement is None:
            payroll = _ensure_payroll_financial_movement(payroll=payroll)
        form = PayrollPaymentForm(instance=payroll.financial_movement, workshop=self.workshop, payroll=payroll)
        return render(request, self.template_name, {"payroll": payroll, "form": form})

    def post(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        payroll = self._get_payroll()
        if payroll.financial_movement is None:
            payroll = _ensure_payroll_financial_movement(payroll=payroll)
        form = PayrollPaymentForm(request.POST, instance=payroll.financial_movement, workshop=self.workshop, payroll=payroll)
        if form.is_valid():
            due_date = form.cleaned_data["due_date"]
            if payroll.due_date != due_date:
                payroll.due_date = due_date
                payroll.save(update_fields=["due_date"])
            movement = form.save()
            if movement.is_paid:
                _mark_payroll_as_paid(payroll=payroll)
            else:
                sync_collaborator_payroll(collaborator=payroll.collaborator, reference_date=_get_payroll_reference_date(payroll=payroll), lock_reference=True)
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
        ).select_related("financial_movement")

        with transaction.atomic():
            for payroll in payrolls:
                _mark_payroll_as_paid(payroll=payroll)

        if request.headers.get("HX-Request"):
            response = HttpResponse()
            response["HX-Refresh"] = "true"
            return response

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
                if payroll.financial_movement is not None and payroll.financial_movement.is_paid:
                    payroll.financial_movement.is_paid = False
                    payroll.financial_movement.save(update_fields=["is_paid"])
                sync_collaborator_payroll(
                    collaborator=payroll.collaborator,
                    reference_date=_get_payroll_reference_date(payroll=payroll),
                    lock_reference=True,
                )
                _unmark_payroll_commissions_as_paid(payroll=payroll)

        if request.headers.get("HX-Request"):
            response = HttpResponse()
            response["HX-Refresh"] = "true"
            return response

        return HttpResponseRedirect(reverse("finance:payroll_list"))
