# ruff: noqa: F403,F405
from apps.budget.forms.layouts.step5 import configure_budget_step5_form
from .base import BudgetStepBaseForm
from .common import *


class BudgetStep5Form(BudgetStepBaseForm):
    slider = forms.IntegerField(required=False, widget=forms.NumberInput(attrs={"class": "w-full centered-range", "type": "range", "min": "-100", "max": "100", "step": "5"}))

    class Meta:
        model = Budget
        fields = ["discount_percentage", "discount_value", "discount_type", "slider"]
        widgets = {
            "discount_percentage": PercentageInput(decimal_places=2, behavior="digit_stream"),
            "discount_value": MoneyInput(),
            "discount_type": RadioButtonGroupInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configure_budget_step5_form(self)

    def clean_discount_value(self):
        discount_value = self.cleaned_data.get("discount_value")
        if discount_value is None:
            return Money(0, "BRL")
        return discount_value

    def clean_discount_percentage(self):
        discount_percentage = self.cleaned_data.get("discount_percentage")
        if discount_percentage is None:
            return Decimal("0")
        return discount_percentage

    def clean_slider(self):
        slider = self.cleaned_data.get("slider")
        if slider is None:
            return 0
        return slider

    def save(self, commit=True):
        budget = super().save(commit=False)
        budget.invalidate_pricing_snapshot_cache()
        resolved_discount_value, resolved_discount_percentage = resolve_discount_fields(
            total_base_value=budget.display_total_base_value,
            discount_value=budget.discount_value,
            discount_percentage=budget.discount_percentage,
        )
        budget.discount_value = resolved_discount_value
        budget.discount_percentage = resolved_discount_percentage
        budget.invalidate_pricing_snapshot_cache()

        if commit:
            budget.save()
        return budget
