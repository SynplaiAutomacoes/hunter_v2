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
)
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class WorkshopForm(forms.ModelForm):
    class Meta:
        model = Workshop
        fields = ["name", "cnpj", "phone", "address", "is_active"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Oficina Hunter"}),
            "cnpj": CPForCNPJInput(mode="cnpj"),
            "phone": PhoneInput(),
            "address": TextInput(attrs={"placeholder": "Rua das Oficinas, 123"}),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        cancel_url = reverse("workshops:list")

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Div(
                Field(Workshop.name.field.name, wrapper_class="w-full"),
                Field(Workshop.cnpj.field.name, wrapper_class="w-full"),
                Field(Workshop.phone.field.name, wrapper_class="w-full"),
                Field(Workshop.address.field.name, wrapper_class="w-full lg:col-span-2"),
                Field(Workshop.is_active.field.name, wrapper_class="w-fit lg:justify-self-end"),
                css_class="grid grid-cols-1 lg:grid-cols-[1fr_1fr_1fr] gap-4 items-start",
            ),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )
