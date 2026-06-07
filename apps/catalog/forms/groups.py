from __future__ import annotations

from django import forms
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.catalog.models.groups import CatalogGroup
from apps.core.presentation.widgets import TextInput
from apps.workshops.models.workshops import Workshop
from apps.core.presentation.forms import CoreModelForm


class CatalogGroupForm(CoreModelForm):
    class Meta:
        model = CatalogGroup
        fields = ["name"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Grupo"}),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = self.get_layout()

    def get_layout(self):
        cancel_url = reverse("catalog:group_list")

        return Layout(
            Div(
                Field("name", wrapper_class="col-span-1"),
                css_class="grid grid-cols-1 gap-4 items-start",
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
            # Validação extra para garantir unicidade case-insensitive no workshop
            qs = CatalogGroup.objects.filter(workshop=self.workshop, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Já existe um grupo com este nome.")
        return name
