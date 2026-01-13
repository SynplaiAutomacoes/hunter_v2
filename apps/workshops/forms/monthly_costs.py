from __future__ import annotations

from django import forms
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.core.widgets import CheckboxInput, TextInput
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshops import Workshop


class MonthlyCostForm(forms.ModelForm):
    class Meta:
        model = MonthlyCost
        fields = ["name", "is_active"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Luz, Água.."}),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = self.get_layout()

    def get_layout(self):
        cancel_url = reverse("workshops:cost_list")

        return Layout(
            Div(
                Field("name", wrapper_class="w-full"),
                Field("is_active", wrapper_class="w-fit"),
                css_class="grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-4 items-start",
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
            qs = MonthlyCost.objects.filter(workshop=self.workshop, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Já existe um custo com este nome.")
        return name
