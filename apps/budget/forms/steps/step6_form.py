# ruff: noqa: F403,F405
from apps.budget.forms.layouts.step6 import configure_budget_step6_form
from .base import BudgetStepBaseForm
from .common import *


class BudgetStep6Form(BudgetStepBaseForm):
    class Meta:
        model = Budget
        fields = ["customer_agreed_departure_at", "service_expected_completion_at"]
        widgets = {
            "customer_agreed_departure_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local", "class": "input-theme h-12"}),
            "service_expected_completion_at": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local", "class": "input-theme h-12"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configure_budget_step6_form(self)

    def clean(self):
        cleaned_data = super().clean() or {}

        customer_agreed_departure_at = cleaned_data.get("customer_agreed_departure_at")
        service_expected_completion_at = cleaned_data.get("service_expected_completion_at")

        if isinstance(customer_agreed_departure_at, datetime) and isinstance(service_expected_completion_at, datetime) and customer_agreed_departure_at < service_expected_completion_at:
            self.add_error("customer_agreed_departure_at", Budget.STEP6_DATE_ORDER_ERROR_MESSAGE)

        return cleaned_data
