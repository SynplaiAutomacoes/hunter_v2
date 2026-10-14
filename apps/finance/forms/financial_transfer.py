from __future__ import annotations

from django import forms
from django.utils import timezone
from djmoney.money import Money

from apps.core.presentation.forms import CoreForm
from apps.core.presentation.widgets import CalendarDateInput, SearchableSelectInput, TextInput, TextareaInput
from apps.finance.forms.emission_ui import format_money
from apps.finance.models.bank_account import BankAccount
from apps.finance.services.financial_transfer import get_transfer_available_balance


class MoneyDecimalField(forms.DecimalField):
    def to_python(self, value):
        if isinstance(value, str):
            normalized = value.strip()
            if "," in normalized:
                normalized = normalized.replace(".", "").replace(",", ".")
            value = normalized
        return super().to_python(value)


class FinancialTransferForm(CoreForm):
    source_account = forms.ModelChoiceField(label="Conta de origem", queryset=BankAccount.objects.none(), widget=SearchableSelectInput())
    destination_account = forms.ModelChoiceField(label="Conta de destino", queryset=BankAccount.objects.none(), widget=SearchableSelectInput())
    transfer_date = forms.DateField(label="Data da transferência", initial=timezone.localdate, widget=CalendarDateInput())
    amount = MoneyDecimalField(label="Valor", min_value=0.01, max_digits=14, decimal_places=2, widget=TextInput(attrs={"placeholder": "0,00", "inputmode": "decimal"}))
    description = forms.CharField(label="Observação", required=False, widget=TextareaInput(rows=3, attrs={"placeholder": "Ex.: transferência para cobrir despesas do caixa"}))

    def __init__(self, *args, workshop, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        accounts = BankAccount.objects.filter(workshop=workshop, is_active=True).order_by("bank_name", "account_number")
        self.fields["source_account"].queryset = accounts
        self.fields["destination_account"].queryset = accounts
        self.available_balance_by_account_id = {
            account.pk: get_transfer_available_balance(workshop=workshop, bank_account=account)
            for account in accounts
        }

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("source_account") and cleaned_data.get("source_account") == cleaned_data.get("destination_account"):
            self.add_error("destination_account", "A conta de destino deve ser diferente da conta de origem.")
        source_account = cleaned_data.get("source_account")
        amount = cleaned_data.get("amount")
        if source_account is not None and amount is not None:
            available_balance = self.available_balance_by_account_id[source_account.pk]
            if amount > available_balance.amount:
                self.add_error("amount", f"O valor excede o saldo disponível da conta de origem ({format_money(available_balance)}).")
        return cleaned_data

    def save(self, *, user):
        from apps.finance.models.financial_transfer import FinancialTransfer

        return FinancialTransfer.objects.create(
            workshop=self.workshop,
            user=user,
            source_account=self.cleaned_data["source_account"],
            destination_account=self.cleaned_data["destination_account"],
            transfer_date=self.cleaned_data["transfer_date"],
            amount=Money(self.cleaned_data["amount"], "BRL"),
            description=self.cleaned_data["description"],
        )
