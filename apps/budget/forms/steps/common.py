# ruff: noqa: F401
from apps.budget.forms.shared import MAX_BUDGET_IMAGES, _get_budget_with_prefetched_items, _render_budget_items_rows, _validate_uploaded_files, _validate_uploaded_images
from apps.budget.forms.widgets import MultipleFileField, MultipleFileInput
from apps.budget.models import Budget, BudgetHistory, BudgetImage, BudgetImageType, BudgetStatus, Defect, SignatureStatus
from apps.budget.pricing import resolve_discount_fields
from apps.checklist.models import Checklist
from apps.collaborators.models import WorkshopCollaborator
from apps.core.presentation.forms import CoreModelForm
from apps.core.presentation.widgets import CalendarDateInput, MoneyInput, NumberInput, PercentageInput, RadioButtonGroupInput, SearchableSelectInput, TextInput, TextareaInput
from apps.core.text_normalization import sentence_case
from apps.core.utils import alert_confirm_layout
from apps.customer.models import Customer, Vehicle
from apps.quote.models.investigative_questions import InvestigativeQuestion, InvestigativeResponse
from apps.workorder.models import WorkOrderDiscountType, WorkOrderStatus
from apps.workshops.util.workshops import has_workshop_perm
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Layout
from django import forms
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from djmoney.money import Money

import base64
import json
from datetime import datetime
from decimal import Decimal
from html import escape
from typing import cast

__all__ = [
    "MAX_BUDGET_IMAGES",
    "_get_budget_with_prefetched_items",
    "_render_budget_items_rows",
    "_validate_uploaded_files",
    "_validate_uploaded_images",
    "MultipleFileField",
    "MultipleFileInput",
    "Budget",
    "BudgetHistory",
    "BudgetImage",
    "BudgetImageType",
    "BudgetStatus",
    "Defect",
    "SignatureStatus",
    "resolve_discount_fields",
    "Checklist",
    "WorkshopCollaborator",
    "CoreModelForm",
    "CalendarDateInput",
    "MoneyInput",
    "NumberInput",
    "PercentageInput",
    "RadioButtonGroupInput",
    "SearchableSelectInput",
    "TextInput",
    "TextareaInput",
    "sentence_case",
    "alert_confirm_layout",
    "Customer",
    "Vehicle",
    "InvestigativeQuestion",
    "InvestigativeResponse",
    "WorkOrderDiscountType",
    "WorkOrderStatus",
    "has_workshop_perm",
    "FormHelper",
    "HTML",
    "Div",
    "Field",
    "Layout",
    "forms",
    "render_to_string",
    "static",
    "reverse",
    "reverse_lazy",
    "timezone",
    "Money",
    "base64",
    "json",
    "datetime",
    "Decimal",
    "escape",
    "cast",
]
