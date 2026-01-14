from __future__ import annotations

from django import forms
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.catalog.models.services import Service
from apps.core.widgets import TextInput, MoneyInput, DurationInput, CheckboxInput
from apps.workshops.models.workshops import Workshop


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ["name", "is_third_party", "duration", "selling_price", "suggested_cost", "description", "is_active"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Troca de Óleo, Alinhamento..."}),
            "is_third_party": CheckboxInput(),
            "duration": DurationInput(),
            "selling_price": MoneyInput(),
            "suggested_cost": MoneyInput(),
            "description": TextInput(),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = self.get_layout()

    def get_layout(self):
        cancel_url = reverse("catalog:services_list")

        return Layout(
            Div(
                # Linha 1: Nome e Checkbox Terceiro
                Field("name", wrapper_class="col-span-12 lg:col-span-10"),
                Field("is_third_party", wrapper_class="col-span-12 lg:col-span-2 text-nowrap"),
                # Linha 2: Valores e Duração
                Field("duration", wrapper_class="col-span-12 lg:col-span-4"),
                Field("suggested_cost", wrapper_class="col-span-12 lg:col-span-4"),
                Field("selling_price", wrapper_class="col-span-12 lg:col-span-4"),
                # Linha 3: Descrição e Ativo
                Field("description", wrapper_class="col-span-12"),
                Field("is_active", wrapper_class="col-span-12"),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start",
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
            qs = Service.objects.filter(workshop=self.workshop, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Já existe um serviço com este nome.")
        return name
