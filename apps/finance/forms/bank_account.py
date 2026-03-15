from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from django import forms
from django.urls import reverse

from apps.core.widgets import TextInput, CheckboxInput, SelectInput
from apps.finance.models.bank_account import BankAccount


class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ["bank_code", "bank_name", "account_type", "agency", "account_number", "is_active"]
        widgets = {
            "bank_code": TextInput(attrs={"placeholder": "Ex: 001"}),
            "bank_name": TextInput(),
            "agency": TextInput(attrs={"placeholder": "0001"}),
            "account_type": SelectInput(),
            "account_number": TextInput(attrs={"placeholder": "12345-6"}),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Div(
                Field("bank_code", wrapper_class="col-span-12 lg:col-span-3"),
                Field("bank_name", wrapper_class="col-span-12 lg:col-span-9"),
                Field("account_type", wrapper_class="col-span-12 lg:col-span-4"),
                Field("agency", wrapper_class="col-span-12 lg:col-span-4"),
                Field("account_number", wrapper_class="col-span-12 lg:col-span-4"),
                Field("is_active", wrapper_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4",
            ),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{reverse("finance:bank_account_list")}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2"
            )
        )