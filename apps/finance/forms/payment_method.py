from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from django import forms
from django.urls import reverse

from apps.core.widgets import CheckboxInput, NumberInput, TextInput, MoneyInput, PercentageInput
from apps.finance.models.payment_method import PaymentMethod


class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = ["description", "installments_count", "tax_percentage", "tax_value", "is_active"]
        widgets = {
            "description": TextInput(attrs={"placeholder": "Ex: Cartão de Crédito, Pix..."}),
            "installments_count": NumberInput(),
            "tax_percentage": PercentageInput(),
            "tax_value": MoneyInput(),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.helper = FormHelper()

        self.helper.layout = Layout(
            Div(
                Field("description", wrapper_class="col-span-12 lg:col-span-12"),
                Field("installments_count", wrapper_class="col-span-12 lg:col-span-3"),

                Div(
                    Div(Field("tax_percentage"), css_class="flex-1"),
                    HTML('<div class="flex items-center justify-center font-bold text-xs opacity-50 px-2 mt-10">OU</div>'),
                    Div(Field("tax_value"), css_class="flex-1"),
                    css_class="col-span-12 lg:col-span-9 flex items-start gap-1",
                ),

                Field("is_active", wrapper_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4",
            ),
            HTML('<div class="divider"></div>'),
            Div(HTML(f'<a href="{reverse("finance:payment_methods_list")}" class="btn-form-cancel">Cancelar</a>'), Submit("submit", "Salvar", css_class="btn-form-save"), css_class="flex items-center justify-end gap-2"),
        )

    def clean(self):
        cleaned_data = super().clean()
        description = cleaned_data.get("description")
        tax_percentage = cleaned_data.get("tax_percentage")
        tax_value = cleaned_data.get("tax_value")

        qs = PaymentMethod.objects.filter(workshop=self.workshop, description=description)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            self.add_error("description", "Já existe uma forma de pagamento com esta descrição nesta Oficina.")

        if tax_percentage and tax_value:
            raise forms.ValidationError("Preencha apenas a taxa em percentual (%) OU a taxa em valor (R$), nunca ambos.")
        return cleaned_data
