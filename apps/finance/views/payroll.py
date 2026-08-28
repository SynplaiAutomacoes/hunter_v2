from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q, Sum
from django.http import HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView
from django.http import HttpResponseRedirect

from django.db import transaction

from djmoney.forms import MoneyField as MoneyFormField
from djmoney.money import Money
from djmoney.forms import MoneyField

from apps.collaborators.models import CollaboratorBenefit, CollaboratorCommissionEntry, CollaboratorPayroll, WorkshopCollaborator
from apps.collaborators.services import (
    PAYROLL_COMPONENT_LABELS,
    add_manual_payroll_benefit,
    add_manual_payroll_commission,
    build_payroll_projection,
    delete_manual_payroll_commission,
    ensure_payroll_component_movements_confirmed,
    ensure_payroll_movements_confirmed,
    ensure_payroll_single_benefit_synced,
    get_payroll_due_date_for_reference,
    get_payroll_movement_diagnosis,
    get_payroll_movement_diagnoses,
    get_reference_work_days,
    get_workshop_work_days,
    mark_payroll_as_paid,
    mark_payroll_as_unpaid,
    mark_payroll_commissions_as_paid,
    mark_payrolls_as_paid,
    mark_payrolls_as_unpaid,
    payroll_has_financial_movements,
    recalculate_payroll_from_linked_movements,
    sync_collaborator_payroll,
    unmark_payroll_commissions_as_paid,
    update_payroll_work_days,
)
from apps.core.presentation.widgets import CalendarDateInput, DecimalInput, MoneyInput, SearchableSelectInput, TextInput, TextareaInput
from apps.finance.models.bank_account import BankAccount
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.financial_movement import BUDGET_PLAN_REQUIRED, apply_payment_reconciliation_rules, create_partial_payment_balance
from apps.finance.views.commissions import MONTH_CHOICES, _parse_int_param, build_paid_status_indicator
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.util.workshops import can_view_payroll_details, get_active_workshop_or_404


class PayrollPaymentForm(forms.ModelForm):
    discount_percentage = forms.DecimalField(
        label="Desconto (%)",
        required=False,
        min_value=Decimal("0.00"),
        max_value=Decimal("100.00"),
        max_digits=5,
        decimal_places=2,
        widget=DecimalInput(min_value=0, max_value=100, decimal_places=2),
    )
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
    is_partial_payment = forms.TypedChoiceField(
        label="Pagamento parcial",
        required=True,
        coerce=lambda value: str(value).lower() == "true",
        choices=((False, "Não"), (True, "Sim")),
        widget=SearchableSelectInput(choices=[(False, "Não"), (True, "Sim")]),
        initial=False,
    )
    partial_payment_amount = MoneyField(label="Valor pago", required=False, widget=MoneyInput())

    class Meta:
        model = FinancialMovement
        fields = [
            "due_date",
            "gross_amount",
            "discount_mode",
            "discount_value",
            "discount_percentage",
            "budget_plan",
            "bank_account",
            "payment_method",
            "is_paid",
            "is_reconciled",
            "nf_number",
            "financial_observation",
        ]
        widgets = {
            "due_date": CalendarDateInput(),
            "gross_amount": MoneyInput(),
            "discount_mode": SearchableSelectInput(),
            "discount_value": MoneyInput(),
            "budget_plan": SearchableSelectInput(),
            "bank_account": SearchableSelectInput(),
            "payment_method": SearchableSelectInput(),
            "nf_number": TextInput(),
            "financial_observation": TextareaInput(rows=3),
        }

    # Fields that remain editable even when the movement is marked as paid.
    PAID_EDITABLE_FIELDS = {"is_paid", "is_reconciled"}

    def __init__(self, *args: Any, workshop=None, **kwargs: Any) -> None:
        payroll: CollaboratorPayroll | None = kwargs.pop("payroll", None)
        data = args[0] if args else kwargs.get("data")
        prefix = str(kwargs.get("prefix") or "")
        if data is not None:
            field_prefix = f"{prefix}-" if prefix else ""
            legacy_amount = f"{field_prefix}amount_0"
            legacy_currency = f"{field_prefix}amount_1"
            gross_amount = f"{field_prefix}gross_amount_0"
            gross_currency = f"{field_prefix}gross_amount_1"
            discount_mode = f"{field_prefix}discount_mode"

            # Payroll edits submitted before Ticket 240 still post ``amount``.
            # Preserve that contract while persisting the new gross/net fields.
            needs_legacy_mapping = bool(data.get(legacy_amount) and not data.get(gross_amount))
            needs_discount_default = bool(
                (data.get(gross_amount) or data.get(legacy_amount)) and not data.get(discount_mode)
            )
            if needs_legacy_mapping or needs_discount_default:
                data = data.copy()

            if needs_legacy_mapping:
                data[gross_amount] = data[legacy_amount]
                if data.get(legacy_currency):
                    data[gross_currency] = data[legacy_currency]

            if needs_discount_default:
                data[discount_mode] = FinancialMovement.DiscountMode.NONE

            if args:
                args = (data, *args[1:])
            else:
                kwargs["data"] = data
        super().__init__(*args, **kwargs)
        self._was_paid = bool(self.instance.pk and self.instance.is_paid)
        self.fields["is_paid"].initial = bool(self.instance.is_paid) if self.instance.pk else False
        self.fields["is_reconciled"].initial = bool(self.instance.is_reconciled) if self.instance.pk else False
        self.fields["budget_plan"].required = True
        self.fields["budget_plan"].error_messages["required"] = BUDGET_PLAN_REQUIRED
        self.fields["bank_account"].required = False
        self.fields["payment_method"].required = False
        self.fields["gross_amount"].required = True
        self.fields["discount_mode"].label = "Tipo de desconto"
        self.fields["discount_mode"].required = True
        payroll_discount_choices = [
            (FinancialMovement.DiscountMode.NONE, "Sem desconto"),
            (FinancialMovement.DiscountMode.AMOUNT, "Desconto em reais (R$)"),
            (FinancialMovement.DiscountMode.PERCENTAGE, "Desconto em percentual (%)"),
        ]
        self.fields["discount_mode"].choices = payroll_discount_choices
        self.fields["discount_mode"].widget.choices = payroll_discount_choices
        self.fields["discount_value"].label = "Desconto (R$)"
        self.fields["discount_value"].required = False
        self.fields["discount_percentage"].required = False
        if self.instance.pk:
            self.initial["discount_percentage"] = Decimal(str(self.instance.discount_percentage or 0)).quantize(Decimal("0.01"))
        if payroll is not None:
            self.fields["due_date"].initial = self.instance.due_date or payroll.due_date
            self.fields["gross_amount"].initial = self.instance.gross_amount or self.instance.amount
        if workshop is not None:
            groups = FinancialGroup.objects.filter(workshop=workshop).order_by("name")
            accounts = BankAccount.objects.filter(workshop=workshop, is_active=True)
            if self.instance.pk and self.instance.bank_account_id:
                accounts = BankAccount.objects.filter(workshop=workshop).filter(
                    Q(is_active=True) | Q(pk=self.instance.bank_account_id)
                )
            accounts = accounts.order_by("bank_name", "account_number", "id").distinct()
            methods = PaymentMethod.objects.filter(workshop=workshop, is_active=True).order_by("description")
            self.fields["budget_plan"].queryset = groups
            self.fields["bank_account"].queryset = accounts
            self.fields["payment_method"].queryset = methods
            self.fields["budget_plan"].widget.choices = [("", "---------")] + [(item.pk, str(item)) for item in groups]
            self.fields["bank_account"].widget.choices = [(item.pk, str(item)) for item in accounts]
            self.fields["payment_method"].widget.choices = [(item.pk, str(item)) for item in methods]

        # Lock non-exempt fields when the movement is already paid.
        self._instance_is_paid = bool(self.instance.pk and self.instance.is_paid)
        if self._instance_is_paid:
            for field_name, field in self.fields.items():
                if field_name not in self.PAID_EDITABLE_FIELDS:
                    field.disabled = True
            # Campos desabilitados não vêm no POST; a instância paga sem plano ainda precisa poder ser desmarcada.
            self.fields["budget_plan"].required = False

    @property
    def is_locked(self) -> bool:
        """Return True when the movement is paid and most fields are disabled."""
        return self._instance_is_paid

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        gross_amount = cleaned_data.get("gross_amount")
        discount_mode = cleaned_data.get("discount_mode")
        discount_value = cleaned_data.get("discount_value")
        discount_percentage = cleaned_data.get("discount_percentage") or Decimal("0.00")

        if gross_amount is not None:
            gross_value = Decimal(str(gross_amount.amount or 0))
            if discount_mode == FinancialMovement.DiscountMode.AMOUNT:
                resolved_discount = Decimal(str(discount_value.amount if discount_value else 0))
                if resolved_discount <= 0:
                    self.add_error("discount_value", "Informe o valor do desconto.")
                elif resolved_discount > gross_value:
                    self.add_error("discount_value", "O desconto não pode ser maior que o valor bruto.")
                cleaned_data["discount_percentage"] = Decimal("0.00")
            elif discount_mode == FinancialMovement.DiscountMode.PERCENTAGE:
                if discount_percentage <= 0:
                    self.add_error("discount_percentage", "Informe o percentual do desconto.")
                elif discount_percentage > Decimal("100"):
                    self.add_error("discount_percentage", "O desconto percentual não pode ser maior que 100%.")
                cleaned_data["discount_value"] = Money(Decimal("0.00"), gross_amount.currency)
            elif discount_mode == FinancialMovement.DiscountMode.NONE:
                cleaned_data["discount_value"] = Money(Decimal("0.00"), gross_amount.currency)
                cleaned_data["discount_percentage"] = Decimal("0.00")
            else:
                self.add_error("discount_mode", "Informe se esta movimentação possui desconto.")

        if cleaned_data.get("is_partial_payment"):
            cleaned_data["is_paid"] = True
            paid_amount = cleaned_data.get("partial_payment_amount")
            total_amount = cleaned_data.get("amount")
            if paid_amount is None:
                self.add_error("partial_payment_amount", "Informe o valor efetivamente pago.")
            elif total_amount is not None and (paid_amount <= Money(0, paid_amount.currency) or paid_amount >= total_amount):
                self.add_error("partial_payment_amount", "O valor pago deve ser maior que zero e menor que o valor total da conta.")
            if self._was_paid:
                self.add_error("is_partial_payment", "Não é possível dividir uma conta que já foi paga.")
        for field, message in apply_payment_reconciliation_rules(cleaned_data):
            self.add_error(field, message)
        return cleaned_data

    def save(self, commit: bool = True) -> FinancialMovement:
        instance = super().save(commit=commit)
        if commit and self.cleaned_data.get("is_partial_payment"):
            create_partial_payment_balance(
                paid_movement=instance,
                paid_amount=self.cleaned_data["partial_payment_amount"],
            )
        return instance


def _bind_widgets_to_html_form(form: forms.Form, form_id: str) -> None:
    """Keep launch fields out of the payroll save form's native validation."""
    for field in form.fields.values():
        field.widget.attrs["form"] = form_id
        widgets = getattr(field.widget, "widgets", None)
        if widgets:
            for widget in widgets:
                widget.attrs["form"] = form_id


class ManualPayrollBenefitForm(forms.Form):
    name = forms.CharField(label="Nome", max_length=255, widget=TextInput(attrs={"placeholder": "Nome do benefício"}))
    amount = MoneyFormField(label="Valor", min_value=Decimal("0.01"), widget=MoneyInput())
    budget_plan = forms.ModelChoiceField(label="Plano orçamentário", queryset=FinancialGroup.objects.none(), widget=SearchableSelectInput())
    description = forms.CharField(label="Descrição", required=False, widget=TextInput(attrs={"placeholder": "Opcional"}))

    def __init__(self, *args: Any, workshop=None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        groups = FinancialGroup.objects.none()
        if workshop is not None:
            groups = FinancialGroup.objects.filter(workshop=workshop).order_by("name")
        self.fields["budget_plan"].queryset = groups
        self.fields["budget_plan"].widget.choices = [("", "Selecione um plano"), *[(item.pk, str(item)) for item in groups]]
        _bind_widgets_to_html_form(self, "payroll-manual-benefit-form")

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        value = Decimal(str(getattr(amount, "amount", amount) or 0))
        if value <= Decimal("0.00"):
            raise forms.ValidationError("Informe um valor maior que zero.")
        return amount


class ManualPayrollCommissionForm(forms.Form):
    amount = MoneyFormField(label="Valor", min_value=Decimal("0.01"), widget=MoneyInput())
    notes = forms.CharField(label="Observação", required=False, widget=TextareaInput(rows=3, attrs={"placeholder": "Motivo (opcional)"}))

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        _bind_widgets_to_html_form(self, "payroll-manual-commission-form")

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        value = Decimal(str(getattr(amount, "amount", amount) or 0))
        if value <= Decimal("0.00"):
            raise forms.ValidationError("Informe um valor maior que zero.")
        return amount


class PayrollAccessMixin:
    def dispatch(self, request, *args, **kwargs):
        workshop = get_active_workshop_or_404(request)
        if not can_view_payroll_details(user=request.user, workshop=workshop, request=request):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class PayrollListView(LoginRequiredMixin, PayrollAccessMixin, WorkshopScopedMixin, TemplateView):
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

    def _get_pending_collaborator_rows(self, *, filters: dict[str, Any], existing_collaborator_ids: set[int]) -> list[dict[str, Any]]:
        if filters["has_modal_date_filter"]:
            return []

        reference_date = date(filters["year"], filters["month"], 1)
        collaborators = list(self._get_active_collaborators_queryset(filters=filters).prefetch_related(Prefetch("benefits", queryset=CollaboratorBenefit.objects.filter(is_active=True, source_payroll__isnull=True))).order_by("name", "id"))
        pending_collaborators = [collaborator for collaborator in collaborators if collaborator.pk not in existing_collaborator_ids]
        if not pending_collaborators:
            return []

        pending_ids = [collaborator.pk for collaborator in pending_collaborators]
        commission_by_collaborator_id: dict[int, Decimal] = {collaborator_id: Decimal("0.00") for collaborator_id in pending_ids}
        for entry in CollaboratorCommissionEntry.objects.filter(
            collaborator_id__in=pending_ids,
            reference_year=filters["year"],
            reference_month=filters["month"],
        ).only("collaborator_id", "commission_amount", "commission_amount_currency"):
            commission_by_collaborator_id[entry.collaborator_id] = commission_by_collaborator_id.get(entry.collaborator_id, Decimal("0.00")) + Decimal(str(entry.commission_amount.amount or 0))

        # All pending collaborators share the same workshop — resolve work days once.
        work_days = get_reference_work_days(collaborator=pending_collaborators[0], reference_date=reference_date)

        rows: list[dict[str, Any]] = []
        for collaborator in pending_collaborators:
            benefits_amount = sum(
                (Decimal(str(benefit.monthly_amount.amount or 0)) for benefit in collaborator.benefits.all()),
                start=Decimal("0.00"),
            )
            commission_amount = commission_by_collaborator_id.get(collaborator.pk, Decimal("0.00"))
            salary_amount = Decimal(str(collaborator.salary.amount or 0))
            transport_amount = Decimal(str((collaborator.transport_allowance_daily_amount * Decimal(work_days)) or 0))
            transport_amount = Money(transport_amount, "BRL").amount
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
        queryset = (
            CollaboratorPayroll.objects.filter(workshop=self.workshop, collaborator__is_active=True)
            .select_related("collaborator", "collaborator__transport_budget_plan", "financial_movement")
            .prefetch_related("financial_movements")
            .order_by("collaborator__name", "id")
        )
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
        diagnoses = get_payroll_movement_diagnoses(payrolls=payrolls)
        rows = []
        for payroll in payrolls:
            is_reconciled = bool(payroll.financial_movement and payroll.financial_movement.is_reconciled)
            diagnosis = diagnoses.get(payroll.pk) or get_payroll_movement_diagnosis(payroll=payroll)
            movements = payroll.get_financial_movements()
            if movements:
                salary_total = Decimal("0.00")
                transport_total = Decimal("0.00")
                benefits_total = Decimal("0.00")
                commission_total = Decimal("0.00")
                for movement in movements:
                    amount = Decimal(str(movement.amount.amount if movement.amount is not None else 0))
                    if movement.payroll_component == FinancialMovement.PayrollComponent.SALARY:
                        salary_total += amount
                    elif movement.payroll_component == FinancialMovement.PayrollComponent.TRANSPORT:
                        transport_total += amount
                    elif movement.payroll_component == FinancialMovement.PayrollComponent.BENEFIT:
                        benefits_total += amount
                    elif movement.payroll_component == FinancialMovement.PayrollComponent.COMMISSION:
                        commission_total += amount
                    else:
                        salary_total += amount
                salary_amount = Money(salary_total, "BRL")
                transport_amount = Money(transport_total, "BRL")
                benefits_amount = Money(benefits_total, "BRL")
                commission_amount = Money(commission_total, "BRL")
                total_amount = Money(salary_total + transport_total + benefits_total + commission_total, "BRL")
            else:
                salary_amount = payroll.salary_amount
                transport_amount = payroll.transport_allowance_amount
                benefits_amount = payroll.benefits_amount
                commission_amount = payroll.commission_amount
                total_amount = payroll.total_amount
            rows.append(
                {
                    "id": payroll.pk,
                    "collaborator_name": payroll.collaborator.name,
                    "due_date": payroll.due_date,
                    "salary_amount": salary_amount,
                    "transport_allowance_amount": transport_amount,
                    "benefits_amount": benefits_amount,
                    "commission_amount": commission_amount,
                    "total_amount": total_amount,
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
        existing_collaborator_ids = set(queryset.values_list("collaborator_id", flat=True))
        pending_rows = self._get_pending_collaborator_rows(filters=filters, existing_collaborator_ids=existing_collaborator_ids)
        context["payroll_rows"] = existing_rows + pending_rows
        totals = queryset.aggregate(total_payroll_amount=Sum("total_amount"), paid_amount=Sum("total_amount", filter=Q(financial_movement__is_paid=True)))
        total_amount = self._money_amount(totals.get("total_payroll_amount"))
        paid_amount = self._money_amount(totals.get("paid_amount"))
        context["pending_amount"] = max(total_amount - paid_amount, Decimal("0.00"))
        context["paid_amount"] = paid_amount
        context["collaborator_filters"] = WorkshopCollaborator.objects.filter(workshop=self.workshop, is_active=True).order_by("name")
        context["bank_account_filters"] = BankAccount.objects.filter(workshop=self.workshop).order_by("bank_name", "account_number", "id")
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


class PayrollEditModalView(LoginRequiredMixin, PayrollAccessMixin, WorkshopScopedMixin, View):
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
            CollaboratorPayroll.objects.select_related("collaborator", "collaborator__transport_budget_plan", "financial_movement").prefetch_related(
                "items",
                "commission_entries__workorder__budget",
                "financial_movements__payroll_benefit",
                "financial_movements__budget_plan",
            ),
            pk=self.kwargs["pk"],
            workshop=self.workshop,
        )

    def _get_existing_payroll(self) -> CollaboratorPayroll | None:
        if "pk" in self.kwargs:
            return self._get_payroll()
        collaborator = self._get_collaborator()
        reference_date = self._get_reference_date()
        return (
            CollaboratorPayroll.objects.select_related("collaborator", "collaborator__transport_budget_plan", "financial_movement")
            .prefetch_related(
                "items",
                "commission_entries__workorder__budget",
                "financial_movements__payroll_benefit",
                "financial_movements__budget_plan",
            )
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
            benefits_total = payroll.benefits_amount if component == FinancialMovement.PayrollComponent.BENEFIT else None
            if component == FinancialMovement.PayrollComponent.BENEFIT and movements:
                movement_total = sum((Decimal(str(movement.amount.amount or 0)) for movement in movements), start=Decimal("0.00"))
                benefits_total = Money(movement_total, "BRL")
            tabs.append(
                {
                    "key": component,
                    "label": PAYROLL_COMPONENT_LABELS.get(component, component),
                    "movements": movements,
                    "has_expected_value": expected,
                    "is_missing": expected and not movements,
                    "is_benefit_tab": component == FinancialMovement.PayrollComponent.BENEFIT,
                    "is_commission_tab": component == FinancialMovement.PayrollComponent.COMMISSION,
                    "benefits_total": benefits_total,
                    "benefit_items": [],
                    "form": None,
                    "default_movement_id": None,
                }
            )
        return tabs

    @staticmethod
    def _get_first_available_financial_tab(component_tabs: list[dict[str, Any]]) -> str:
        for tab in component_tabs:
            if tab["movements"]:
                return str(tab["key"])
        return "summary"

    def _build_component_url(
        self,
        *,
        payroll: CollaboratorPayroll,
        tab: str,
        movement_id: int | None = None,
        continue_without_create: bool = False,
        prompt_create_component: str | None = None,
        show_manual_benefit_form: bool = False,
        show_manual_commission_form: bool = False,
    ) -> str:
        params = QueryDict("", mutable=True)
        params["tab"] = tab
        if movement_id is not None:
            params["movement_id"] = str(movement_id)
        if continue_without_create:
            params["continue_without_create"] = "true"
        if prompt_create_component:
            params["prompt_create_component"] = prompt_create_component
        if show_manual_benefit_form:
            params["show_manual_benefit_form"] = "true"
        if show_manual_commission_form:
            params["show_manual_commission_form"] = "true"
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

    @staticmethod
    def _component_form_prefix(component: str, movement_id: int | None = None) -> str:
        if component == FinancialMovement.PayrollComponent.BENEFIT and movement_id is not None:
            return f"comp_{component}_{movement_id}"
        return f"comp_{component}"

    @staticmethod
    def _benefit_display_name(*, movement: FinancialMovement) -> str:
        benefit = getattr(movement, "payroll_benefit", None)
        benefit_name = str(getattr(benefit, "name", "") or "").strip()
        if benefit_name:
            return benefit_name
        description = str(movement.description or "").strip()
        if description:
            return description.split(" - ")[0].strip() or PAYROLL_COMPONENT_LABELS[FinancialMovement.PayrollComponent.BENEFIT]
        return PAYROLL_COMPONENT_LABELS[FinancialMovement.PayrollComponent.BENEFIT]

    def _build_benefit_items(
        self,
        *,
        payroll: CollaboratorPayroll,
        movements: list[FinancialMovement],
        post_data: Any | None = None,
        failed_forms: dict[int, PayrollPaymentForm] | None = None,
    ) -> list[dict[str, Any]]:
        benefit_items: list[dict[str, Any]] = []
        for movement in movements:
            prefix = self._component_form_prefix(FinancialMovement.PayrollComponent.BENEFIT, movement.pk)
            if failed_forms is not None and movement.pk in failed_forms:
                form = failed_forms[movement.pk]
            elif post_data is not None:
                form = PayrollPaymentForm(post_data, instance=movement, workshop=self.workshop, payroll=payroll, prefix=prefix)
            else:
                form = PayrollPaymentForm(instance=movement, workshop=self.workshop, payroll=payroll, prefix=prefix)
            benefit_items.append(
                {
                    "movement": movement,
                    "movement_id": movement.pk,
                    "benefit_name": self._benefit_display_name(movement=movement),
                    "amount": movement.amount,
                    "form": form,
                    "prefix": prefix,
                }
            )
        return benefit_items

    def _manual_launch_template_context(
        self,
        *,
        payroll: CollaboratorPayroll,
        manual_benefit_form: ManualPayrollBenefitForm | None = None,
        manual_commission_form: ManualPayrollCommissionForm | None = None,
        show_manual_benefit_form: bool = False,
        show_manual_commission_form: bool = False,
    ) -> dict[str, Any]:
        return {
            "payroll_is_paid": payroll.status == CollaboratorPayroll.Status.PAID,
            "manual_benefit_form": manual_benefit_form or ManualPayrollBenefitForm(workshop=self.workshop, prefix="manual_benefit"),
            "manual_commission_form": manual_commission_form or ManualPayrollCommissionForm(prefix="manual_commission"),
            "show_manual_benefit_form": show_manual_benefit_form,
            "show_manual_commission_form": show_manual_commission_form,
        }

    def _open_edit_modal(
        self,
        *,
        request: Any,
        payroll: CollaboratorPayroll,
        selected_tab: str | None = None,
        force_selected_tab: bool = False,
        manual_benefit_form: ManualPayrollBenefitForm | None = None,
        manual_commission_form: ManualPayrollCommissionForm | None = None,
        show_manual_benefit_form: bool = False,
        show_manual_commission_form: bool = False,
    ) -> HttpResponse:
        component_tabs = self._build_component_tabs(payroll=payroll)
        selected_tab = selected_tab or self._get_requested_tab()
        fallback_tab = self._get_first_available_financial_tab(component_tabs)

        if selected_tab not in {"collaborator", "commissions_history", "summary"}:
            active_component_tab = next((tab for tab in component_tabs if tab["key"] == selected_tab), None)
            if active_component_tab is None:
                selected_tab = fallback_tab
            elif not force_selected_tab and active_component_tab["is_missing"] and not active_component_tab["movements"]:
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
            tab["default_movement_id"] = movement_id
            if tab["is_benefit_tab"]:
                tab["benefit_items"] = self._build_benefit_items(payroll=payroll, movements=tab["movements"])
                tab["form"] = None
                tab["manual_launch_open_url"] = self._build_component_url(
                    payroll=payroll,
                    tab=str(tab["key"]),
                    continue_without_create=True,
                    show_manual_benefit_form=True,
                )
                tab["manual_launch_close_url"] = self._build_component_url(
                    payroll=payroll,
                    tab=str(tab["key"]),
                    continue_without_create=True,
                )
                continue
            if tab["is_commission_tab"]:
                tab["manual_launch_open_url"] = self._build_component_url(
                    payroll=payroll,
                    tab=str(tab["key"]),
                    continue_without_create=True,
                    show_manual_commission_form=True,
                )
                tab["manual_launch_close_url"] = self._build_component_url(
                    payroll=payroll,
                    tab=str(tab["key"]),
                    continue_without_create=True,
                )
            movement = next((m for m in tab["movements"] if m.pk == movement_id), None) if movement_id is not None else None
            prefix = self._component_form_prefix(str(tab["key"]))
            tab["form"] = PayrollPaymentForm(instance=movement, workshop=self.workshop, payroll=payroll, prefix=prefix) if movement is not None else None

        benefit_tab = next((tab for tab in component_tabs if tab["is_benefit_tab"]), None)
        default_benefit_movement_id = benefit_tab["default_movement_id"] if benefit_tab is not None else None

        from apps.workorder.models import WorkOrder
        from apps.collaborators.models import CollaboratorCommissionEntry
        
        warranty_wos_qs = WorkOrder.objects.filter(
            workshop=payroll.workshop,
            budget_type="warranty",
            warranty_origin__isnull=False,
            criado_em__year=payroll.reference_year,
            criado_em__month=payroll.reference_month
        ).select_related("warranty_origin")
        
        prejuizo_total = Decimal("0.00")
        warranty_wos = []
        for w_wo in warranty_wos_qs:
            entries = list(CollaboratorCommissionEntry.objects.filter(
                collaborator=payroll.collaborator,
                workorder=w_wo.warranty_origin
            ).select_related("workorder"))
            loss = sum((e.commission_amount.amount for e in entries if e.commission_amount), start=Decimal("0.00"))
            if loss > 0:
                prejuizo_total += loss
                warranty_wos.append({"workorder": w_wo, "entries": entries})
                
        prejuizo_money = Money(-prejuizo_total, "BRL")

        return render(
            request,
            "finance/payroll/partials/edit_modal.html",
            {
                "payroll": payroll,
                "selected_tab": selected_tab,
                "component_tabs": component_tabs,
                "modal_url": modal_url,
                "fallback_tab": fallback_tab,
                "continue_without_create": True,
                "default_benefit_movement_id": default_benefit_movement_id,
                "warranty_wos": warranty_wos,
                "prejuizo_total": prejuizo_money,
                "workshop_default_work_days": get_workshop_work_days(
                    workshop=payroll.workshop,
                    reference_date=date(payroll.reference_year, payroll.reference_month, 1),
                ),
                "transport_daily_amount": payroll.collaborator.transport_allowance_daily_amount,
                **self._manual_launch_template_context(
                    payroll=payroll,
                    manual_benefit_form=manual_benefit_form,
                    manual_commission_form=manual_commission_form,
                    show_manual_benefit_form=show_manual_benefit_form,
                    show_manual_commission_form=show_manual_commission_form,
                ),
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

        return self._open_edit_modal(
            request=request,
            payroll=payroll,
            show_manual_benefit_form=request.GET.get("show_manual_benefit_form") == "true",
            show_manual_commission_form=request.GET.get("show_manual_commission_form") == "true",
        )

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
            response = self._open_edit_modal(request=request, payroll=target_payroll)
            response["HX-Trigger"] = json.dumps({"payrollListRefresh": True})
            return response

        if payroll is None or not payroll_has_financial_movements(payroll=payroll) or payroll.financial_movement is None:
            return self._build_confirmation_response(request=request, collaborator=collaborator, payroll=payroll)

        raw_work_days = str(request.POST.get("work_days") or "").strip()
        parsed_work_days: int | None
        if raw_work_days == "":
            parsed_work_days = None
            work_days_requested = True
        else:
            try:
                parsed_work_days = int(raw_work_days)
            except (TypeError, ValueError):
                parsed_work_days = None
                work_days_requested = False
            else:
                work_days_requested = parsed_work_days >= 0

        component_tabs = self._build_component_tabs(payroll=payroll)
        all_forms: list[tuple[str, PayrollPaymentForm]] = []
        invalid_forms: list[tuple[str, PayrollPaymentForm]] = []
        failed_benefit_forms: dict[int, PayrollPaymentForm] = {}

        for tab in component_tabs:
            if not tab["movements"]:
                continue
            if tab["is_benefit_tab"]:
                for movement in tab["movements"]:
                    prefix = self._component_form_prefix(str(tab["key"]), movement.pk)
                    form = PayrollPaymentForm(request.POST, instance=movement, workshop=self.workshop, payroll=payroll, prefix=prefix)
                    has_tab_data = any(str(key).startswith(prefix) for key in request.POST.keys())
                    if not has_tab_data:
                        continue
                    if form.is_valid():
                        all_forms.append((tab["key"], form))
                    else:
                        invalid_forms.append((tab["key"], form))
                        failed_benefit_forms[movement.pk] = form
                continue

            movement = tab["movements"][0]
            prefix = self._component_form_prefix(str(tab["key"]))
            form = PayrollPaymentForm(request.POST, instance=movement, workshop=self.workshop, payroll=payroll, prefix=prefix)
            has_tab_data = any(str(key).startswith(prefix) for key in request.POST.keys())
            if not has_tab_data:
                continue
            if form.is_valid():
                all_forms.append((tab["key"], form))
            else:
                invalid_forms.append((tab["key"], form))

        if invalid_forms:
            modal_url = self._get_modal_url(payroll=payroll)
            fallback_tab = self._get_first_available_financial_tab(component_tabs)
            selected_tab_retry = self._get_requested_tab()
            if selected_tab_retry not in {"collaborator", "commissions_history", "summary"}:
                active_tab = next((tab for tab in component_tabs if tab["key"] == selected_tab_retry), None)
                if active_tab is None or active_tab["is_missing"]:
                    selected_tab_retry = fallback_tab
            for tab in component_tabs:
                if not tab["movements"]:
                    continue
                tab["default_movement_id"] = tab["movements"][0].pk
                if tab["is_benefit_tab"]:
                    tab["benefit_items"] = self._build_benefit_items(
                        payroll=payroll,
                        movements=tab["movements"],
                        failed_forms=failed_benefit_forms,
                    )
                    tab["form"] = None
                    continue
                prefix = self._component_form_prefix(str(tab["key"]))
                failed_form = next((f for key, f in invalid_forms if key == tab["key"]), None)
                if failed_form is not None:
                    tab["form"] = failed_form
                else:
                    tab["form"] = PayrollPaymentForm(instance=tab["movements"][0], workshop=self.workshop, payroll=payroll, prefix=prefix)
            return render(
                request,
                self.template_name,
                {
                    "payroll": payroll,
                    "selected_tab": selected_tab_retry,
                    "component_tabs": component_tabs,
                    "modal_url": modal_url,
                    "fallback_tab": fallback_tab,
                    "continue_without_create": True,
                    "default_benefit_movement_id": next((tab["default_movement_id"] for tab in component_tabs if tab["is_benefit_tab"]), None),
                    "workshop_default_work_days": get_workshop_work_days(
                        workshop=payroll.workshop,
                        reference_date=date(payroll.reference_year, payroll.reference_month, 1),
                    ),
                    "transport_daily_amount": payroll.collaborator.transport_allowance_daily_amount,
                    **self._manual_launch_template_context(payroll=payroll),
                },
            )

        work_days_changed = False
        if all_forms or work_days_requested:
            with transaction.atomic():
                for _component_key, form in all_forms:
                    form.save()
                if all_forms:
                    recalculate_payroll_from_linked_movements(payroll=payroll)
                # Apply work days after form saves so payment-tab POST data does not overwrite VT.
                # Submitting the current work_days value (always present in the form) must not
                # mark the payroll as custom or trigger a full sync that reverts amount/plan.
                if work_days_requested:
                    previous_work_days = int(payroll.work_days or 0)
                    previous_is_custom = bool(payroll.work_days_is_custom)
                    workshop_default_work_days = get_workshop_work_days(
                        workshop=payroll.workshop,
                        reference_date=date(payroll.reference_year, payroll.reference_month, 1),
                    )
                    if parsed_work_days is None:
                        resolved_work_days = workshop_default_work_days
                        proposed_is_custom = False
                    else:
                        resolved_work_days = max(0, int(parsed_work_days))
                        if resolved_work_days == previous_work_days:
                            proposed_is_custom = previous_is_custom
                        else:
                            proposed_is_custom = resolved_work_days != workshop_default_work_days
                    work_days_changed = previous_is_custom != proposed_is_custom or previous_work_days != resolved_work_days
                    if work_days_changed:
                        payroll = update_payroll_work_days(
                            payroll=payroll,
                            work_days=parsed_work_days,
                            sync_salary_costs=False,
                            resync_components=False,
                        )
                payroll.refresh_from_db()

                movements = payroll.get_financial_movements()
                if any(movement.is_paid for movement in movements):
                    mark_payroll_commissions_as_paid(payroll=payroll, paid_at=timezone.localdate())
                else:
                    unmark_payroll_commissions_as_paid(payroll=payroll)
                payroll.refresh_from_db()

            response = self._open_edit_modal(request=request, payroll=payroll, selected_tab=self._get_requested_tab())
            toast_message = "Folha atualizada com sucesso."
            if work_days_changed and not all_forms:
                toast_message = "Dias úteis atualizados com sucesso."
            response["HX-Trigger"] = json.dumps(
                {
                    "showToast": {"message": toast_message, "type": "success"},
                    "payrollListRefresh": True,
                }
            )
            return response

        return self._open_edit_modal(request=request, payroll=payroll)


class PayrollSyncComponentView(PayrollEditModalView):
    """Sync a single payroll tab (component) for one collaborator.

    GET renders a confirmation dialog scoped to the active tab; POST (``confirm=true``)
    recalculates only that component and re-renders the payroll edit modal.
    """

    template_name = "finance/payroll/partials/sync_component_confirm_modal.html"
    ALLOWED_COMPONENTS = {
        FinancialMovement.PayrollComponent.SALARY,
        FinancialMovement.PayrollComponent.TRANSPORT,
        FinancialMovement.PayrollComponent.BENEFIT,
        FinancialMovement.PayrollComponent.COMMISSION,
    }

    def _get_component(self) -> str:
        return str(self.kwargs["component"])

    def _get_movement_id(self) -> int | None:
        raw = self.request.GET.get("movement_id") or self.request.POST.get("movement_id")
        if raw is not None:
            try:
                return int(raw)
            except (TypeError, ValueError):
                pass
        return None

    def _resolve_benefit_label(self, *, payroll: CollaboratorPayroll, movement_id: int | None) -> str:
        if movement_id is None:
            return PAYROLL_COMPONENT_LABELS.get(FinancialMovement.PayrollComponent.BENEFIT, "Benefícios")
        movement = payroll.financial_movements.filter(pk=movement_id, payroll_component=FinancialMovement.PayrollComponent.BENEFIT).first()
        if movement is not None:
            return self._benefit_display_name(movement=movement)
        return PAYROLL_COMPONENT_LABELS.get(FinancialMovement.PayrollComponent.BENEFIT, "Benefícios")

    def get(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        payroll = self._get_payroll()
        collaborator = payroll.collaborator
        component = self._get_component()
        movement_id = self._get_movement_id()

        if component == FinancialMovement.PayrollComponent.BENEFIT and movement_id is not None:
            component_label = self._resolve_benefit_label(payroll=payroll, movement_id=movement_id)
        else:
            component_label = PAYROLL_COMPONENT_LABELS.get(component, component)

        post_url = request.get_full_path()

        return render(
            request,
            self.template_name,
            {
                "payroll": payroll,
                "collaborator": collaborator,
                "component": component,
                "component_label": component_label,
                "post_url": post_url,
                "sync_url": reverse("finance:payroll_sync_component", kwargs={"pk": payroll.pk, "component": component}),
            },
        )

    def post(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        payroll = self._get_payroll()
        component = self._get_component()
        movement_id = self._get_movement_id()

        if component == FinancialMovement.PayrollComponent.BENEFIT and movement_id is not None:
            component_label = self._resolve_benefit_label(payroll=payroll, movement_id=movement_id)
        else:
            component_label = PAYROLL_COMPONENT_LABELS.get(component, component)

        if component not in self.ALLOWED_COMPONENTS:
            return _build_hx_toast_response(message="Componente invalido para sincronizacao.", toast_type="warning", status=400)

        if payroll.status == CollaboratorPayroll.Status.PAID:
            return _build_hx_toast_response(message="A folha paga nao pode ser sincronizada.", toast_type="warning", status=400)

        component_tabs = {str(tab["key"]): tab for tab in self._build_component_tabs(payroll=payroll)}
        active_tab = component_tabs.get(component)
        if active_tab is None or not active_tab["movements"]:
            return _build_hx_toast_response(
                message="Esta aba nao possui movimentacoes para sincronizar.",
                toast_type="warning",
                status=400,
            )

        if component == FinancialMovement.PayrollComponent.BENEFIT and movement_id is not None:
            payroll = ensure_payroll_single_benefit_synced(payroll=payroll, movement_id=movement_id)
        else:
            payroll = ensure_payroll_component_movements_confirmed(payroll=payroll, component=component)
        response = self._open_edit_modal(request=request, payroll=payroll, selected_tab=component)
        response["HX-Trigger"] = json.dumps(
            {
                "showToast": {"message": f"{component_label} sincronizado com sucesso.", "type": "success"},
                "payrollListRefresh": True,
            }
        )
        return response


class PayrollAddManualBenefitView(PayrollEditModalView):
    def post(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        payroll = self._get_payroll()
        form = ManualPayrollBenefitForm(request.POST, workshop=self.workshop, prefix="manual_benefit")
        if payroll.status == CollaboratorPayroll.Status.PAID:
            return _build_hx_toast_response(message="A folha paga não pode receber lançamentos manuais.", toast_type="warning", status=400)
        if not form.is_valid():
            return self._open_edit_modal(
                request=request,
                payroll=payroll,
                selected_tab=FinancialMovement.PayrollComponent.BENEFIT,
                force_selected_tab=True,
                manual_benefit_form=form,
                show_manual_benefit_form=True,
            )
        try:
            add_manual_payroll_benefit(
                payroll=payroll,
                name=str(form.cleaned_data["name"]),
                amount=form.cleaned_data["amount"],
                budget_plan=form.cleaned_data["budget_plan"],
                description=str(form.cleaned_data.get("description") or ""),
            )
        except ValueError as exc:
            return _build_hx_toast_response(message=str(exc), toast_type="warning", status=400)

        payroll = self._get_payroll()
        response = self._open_edit_modal(
            request=request,
            payroll=payroll,
            selected_tab=FinancialMovement.PayrollComponent.BENEFIT,
            force_selected_tab=True,
            show_manual_benefit_form=False,
        )
        response["HX-Trigger"] = json.dumps(
            {
                "showToast": {"message": "Benefício lançado nesta competência.", "type": "success"},
                "payrollListRefresh": True,
            }
        )
        return response


class PayrollAddManualCommissionView(PayrollEditModalView):
    def post(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        payroll = self._get_payroll()
        form = ManualPayrollCommissionForm(request.POST, prefix="manual_commission")
        if payroll.status == CollaboratorPayroll.Status.PAID:
            return _build_hx_toast_response(message="A folha paga não pode receber lançamentos manuais.", toast_type="warning", status=400)
        if not form.is_valid():
            return self._open_edit_modal(
                request=request,
                payroll=payroll,
                selected_tab=FinancialMovement.PayrollComponent.COMMISSION,
                force_selected_tab=True,
                manual_commission_form=form,
                show_manual_commission_form=True,
            )
        try:
            add_manual_payroll_commission(
                payroll=payroll,
                amount=form.cleaned_data["amount"],
                notes=str(form.cleaned_data.get("notes") or ""),
            )
        except ValueError as exc:
            return _build_hx_toast_response(message=str(exc), toast_type="warning", status=400)

        payroll = self._get_payroll()
        response = self._open_edit_modal(
            request=request,
            payroll=payroll,
            selected_tab=FinancialMovement.PayrollComponent.COMMISSION,
            force_selected_tab=True,
            show_manual_commission_form=False,
        )
        response["HX-Trigger"] = json.dumps(
            {
                "showToast": {"message": "Comissão lançada nesta competência.", "type": "success"},
                "payrollListRefresh": True,
            }
        )
        return response


class PayrollDeleteManualCommissionView(PayrollEditModalView):
    def post(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        payroll = self._get_payroll()
        entry = get_object_or_404(
            CollaboratorCommissionEntry,
            pk=self.kwargs["entry_pk"],
            collaborator=payroll.collaborator,
            reference_year=payroll.reference_year,
            reference_month=payroll.reference_month,
            origin=CollaboratorCommissionEntry.Origin.MANUAL,
        )
        try:
            delete_manual_payroll_commission(payroll=payroll, entry=entry)
        except ValueError as exc:
            return _build_hx_toast_response(message=str(exc), toast_type="warning", status=400)

        payroll = self._get_payroll()
        response = self._open_edit_modal(
            request=request,
            payroll=payroll,
            selected_tab="commissions_history",
            force_selected_tab=True,
        )
        response["HX-Trigger"] = json.dumps(
            {
                "showToast": {"message": "Comissão manual excluída.", "type": "success"},
                "payrollListRefresh": True,
            }
        )
        return response


class PayrollBulkPayView(LoginRequiredMixin, PayrollAccessMixin, WorkshopScopedMixin, View):
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

        payrolls = list(
            CollaboratorPayroll.objects.filter(
                pk__in=payroll_ids,
                workshop=self.workshop,
            )
            .select_related("collaborator", "financial_movement")
            .prefetch_related("financial_movements")
        )

        with transaction.atomic():
            _, skipped_collaborators = mark_payrolls_as_paid(payrolls=payrolls, paid_at=timezone.localdate())

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


class PayrollBulkUnpayView(LoginRequiredMixin, PayrollAccessMixin, WorkshopScopedMixin, View):
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

        payrolls = list(
            CollaboratorPayroll.objects.filter(
                pk__in=payroll_ids,
                workshop=self.workshop,
            )
            .select_related("collaborator", "financial_movement")
            .prefetch_related("financial_movements")
        )

        with transaction.atomic():
            mark_payrolls_as_unpaid(payrolls=payrolls)

        if request.headers.get("HX-Request"):
            response = HttpResponse()
            response["HX-Refresh"] = "true"
            return response

        return HttpResponseRedirect(reverse("finance:payroll_list"))


class PayrollBulkConciliateView(LoginRequiredMixin, WorkshopScopedMixin, View):
    workshop_permission_app_label = "finance"
    workshop_permission_model = "financialmovement"
    workshop_permission_codename = "change_financialmovement"

    def post(self, request, *args, **kwargs):
        raw_values = request.POST.getlist("payroll_ids")
        bank_account_id = str(request.POST.get("bank_account_id") or "").strip()
        if not raw_values:
            return HttpResponse("Nenhuma folha selecionada.", status=400)
        if not bank_account_id:
            return HttpResponse("Selecione uma conta bancária.", status=400)

        payroll_ids: list[int] = []
        for value in raw_values:
            try:
                payroll_ids.append(int(value))
            except (TypeError, ValueError):
                pass

        if not payroll_ids:
            return HttpResponse("Nenhuma folha selecionada.", status=400)

        bank_account = get_object_or_404(BankAccount, workshop=self.workshop, pk=bank_account_id)
        payrolls = (
            CollaboratorPayroll.objects.filter(
                pk__in=payroll_ids,
                workshop=self.workshop,
            )
            .select_related("collaborator", "financial_movement")
            .prefetch_related("financial_movements")
        )

        skipped: list[str] = []
        with transaction.atomic():
            for payroll in payrolls:
                movements = payroll.get_financial_movements()
                if not movements:
                    skipped.append(f"{payroll.collaborator.name}: sem movimentações")
                    continue
                if any(not movement.is_paid for movement in movements):
                    skipped.append(f"{payroll.collaborator.name}: pagamento pendente")
                    continue
                if any(not movement.budget_plan_id for movement in movements):
                    skipped.append(f"{payroll.collaborator.name}: plano orçamentário pendente")
                    continue

                movement_ids = [movement.pk for movement in movements if movement.pk is not None and not movement.is_reconciled]
                if not movement_ids:
                    continue

                FinancialMovement.objects.filter(pk__in=movement_ids).update(is_reconciled=True, bank_account=bank_account)

        if request.headers.get("HX-Request"):
            if skipped:
                return _build_hx_toast_response(
                    message="Algumas folhas não puderam ser conciliadas: " + "; ".join(skipped[:3]) + ("..." if len(skipped) > 3 else ""),
                    toast_type="warning",
                    refresh=True,
                )
            response = HttpResponse()
            response["HX-Refresh"] = "true"
            return response

        if skipped:
            messages.warning(request, "Algumas folhas não puderam ser conciliadas: " + "; ".join(skipped[:3]) + ("..." if len(skipped) > 3 else ""))

        return HttpResponseRedirect(reverse("finance:payroll_list"))
