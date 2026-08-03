from __future__ import annotations

from django import forms
from django.urls import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Field, HTML, Layout, Submit

from apps.core.presentation.forms import CoreModelForm
from apps.core.presentation.widgets import CheckboxInput, NumberInput, TextInput
from apps.workshops.models.review_plans import ReviewPlan
from apps.workshops.models.workshops import Workshop


class ReviewPlanForm(CoreModelForm):
    class Meta:
        model = ReviewPlan
        fields = ["name", "validity_days", "validity_km", "notification_lead_days", "repeat_notification", "is_active"]
        widgets = {
            "name": TextInput(attrs={"placeholder": "Ex: Sintético 5W30"}),
            "validity_days": NumberInput(),
            "validity_km": NumberInput(),
            "notification_lead_days": NumberInput(),
            "repeat_notification": CheckboxInput(),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.layout = self.get_layout()

    def get_layout(self):
        cancel_url = reverse("workshops:review_plan_list")

        return Layout(
            Div(
                Field("name", wrapper_class="col-span-12"),
                Field("validity_days", wrapper_class="col-span-12 lg:col-span-4"),
                Field("validity_km", wrapper_class="col-span-12 lg:col-span-4"),
                Field("notification_lead_days", wrapper_class="col-span-12 lg:col-span-4"),
                Field("repeat_notification", wrapper_class="col-span-12"),
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
            qs = ReviewPlan.objects.filter(workshop=self.workshop, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("Já existe um plano de revisão com este nome.")
        return name


class QuickReviewPlanForm(ReviewPlanForm):
    """Review plan form for HTMX quick-create/update modal (no outer form tag/buttons)."""

    class Meta(ReviewPlanForm.Meta):
        fields = ["name", "validity_days", "validity_km", "notification_lead_days"]

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, workshop=workshop, **kwargs)
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Div(
                Field("name", wrapper_class="col-span-12 md:col-span-6 min-w-[18rem]"),
                Field("notification_lead_days", wrapper_class="col-span-12 md:col-span-6 min-w-[18rem]"),
                Field("validity_days", wrapper_class="col-span-12 md:col-span-6 min-w-[18rem]"),
                Field("validity_km", wrapper_class="col-span-12 md:col-span-6 min-w-[18rem]"),
                css_class="grid grid-cols-12 gap-x-4 gap-y-3 items-start",
            ),
        )

    def save(self, commit: bool = True):
        instance = super().save(commit=False)
        instance.is_active = True
        if commit:
            instance.save()
            self.save_m2m()
        return instance
