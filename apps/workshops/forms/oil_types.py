from __future__ import annotations

from django import forms
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.core.presentation.forms import CoreModelForm
from apps.core.presentation.widgets import CheckboxInput, NumberInput, TextInput
from apps.workshops.models.oil_types import OilType
from apps.workshops.models.workshops import Workshop


class OilTypeForm(CoreModelForm):
    class Meta:
        model = OilType
        fields = ["name", "validity_days", "validity_km", "notification_lead_days", "is_active"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Sintético 5W30"}),
            "validity_days": NumberInput(),
            "validity_km": NumberInput(),
            "notification_lead_days": NumberInput(),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = self.get_layout()

    def get_layout(self):
        cancel_url = reverse("workshops:oil_type_list")

        return Layout(
            Div(
                Field("name", wrapper_class="col-span-12"),
                Field("validity_days", wrapper_class="col-span-12 lg:col-span-4"),
                Field("validity_km", wrapper_class="col-span-12 lg:col-span-4"),
                Field("notification_lead_days", wrapper_class="col-span-12 lg:col-span-4"),
                Field("is_active", wrapper_class="col-span-12"),
                css_class="grid grid-cols-12 gap-4",
            ),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if name and self.workshop:
            qs = OilType.objects.filter(workshop=self.workshop, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Já existe um tipo de óleo com este nome.")
        return name
