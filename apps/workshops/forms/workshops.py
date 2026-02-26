from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.core.widgets import (
    CheckboxInput,
    CPForCNPJInput,
    PhoneInput,
    TextInput,
    PasswordInput,
)
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class WorkshopForm(forms.ModelForm):
    class Meta:
        model = Workshop
        fields = ["name", "cnpj", "phone", "address", "uf", "is_active", "pfx_certificate", "certificate_password"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Oficina Hunter"}),
            "cnpj": CPForCNPJInput(mode="cnpj"),
            "phone": PhoneInput(),
            "address": TextInput(attrs={"placeholder": "Rua das Oficinas, 123"}),
            "uf": TextInput(attrs={"placeholder": "SP"}),
            "is_active": CheckboxInput(),
            "certificate_password": PasswordInput(render_value=True),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.instance.pk and not self.data:
            self.initial["uf"] = ""

        cancel_url = reverse("workshops:list")

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Div(
                Field("name", wrapper_class="col-span-12 lg:col-span-6"),
                Field("cnpj", wrapper_class="col-span-12 lg:col-span-6"),
                Field("phone", wrapper_class="col-span-12 lg:col-span-6"),
                Field("address", wrapper_class="col-span-12 lg:col-span-6"),
                Field("uf", wrapper_class="col-span-12 lg:col-span-6"),
                Field("is_active", wrapper_class="col-span-12 lg:col-span-6"),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
            ),
            HTML('<div class="divider text-sm opacity-50">Integração SEFAZ</div>'),
            Div(
                Field("pfx_certificate", wrapper_class="w-full file-input-primary"),
                Field("certificate_password", wrapper_class="w-full"),
                css_class="grid grid-cols-1 lg:grid-cols-2 gap-4",
            ),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )
