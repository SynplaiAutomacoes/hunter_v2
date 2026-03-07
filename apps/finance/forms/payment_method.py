from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit
from django import forms
from django.urls import reverse

from apps.core.widgets import TextInput, CheckboxInput
from apps.finance.models.payment_method import PaymentMethod


class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = ["description", "is_active"]
        widgets = {
            "description": TextInput(attrs={"placeholder": "Ex: Cartão de Crédito, Pix..."}),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Div(
                Field("description", wrapper_class="col-span-12 lg:col-span-9"),
                Field("is_active", wrapper_class="col-span-12 lg:col-span-3"),
                css_class="grid grid-cols-12 gap-4"
            ),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{reverse("finance:payment_methods_list")}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2"
            )
        )