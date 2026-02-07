import json
import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import parse_qs, urlparse

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.generic import CreateView, DeleteView, ListView, TemplateView
from djmoney.money import Money

from apps.budget.forms import BudgetItemEditForm, BudgetStep1Form, BudgetStep2Form, BudgetStep3Form, BudgetStep4Form, BudgetStep5Form, BudgetStep6Form, LocalServiceForm, LocalProductForm
from apps.budget.models import Budget, BudgetItem, BudgetStatus
from apps.budget.utils import HtmxResponseHelper
from apps.budget.fields import DurationField
from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.forms import MultiStepFormMixin
from apps.core.tables import TableActionDefaults
from apps.core.templatetags.table_tags import TableColumn
from apps.core.views import HtmxDeleteResponseMixin, HtmxTemplateResponseMixin
from apps.customer.models import Customer, Vehicle
from apps.workshops.mixin import WorkshopScopedMixin
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.util.workshops import get_active_workshop_or_404

logger = logging.getLogger(__name__)

def _get_budget_for_workshop(workshop, budget_id):
    return get_object_or_404(Budget, id=budget_id, workshop=workshop)


def _get_budget_item_for_workshop(workshop, budget_id, item_id, **extra_filters):
    return get_object_or_404(
        BudgetItem,
        id=item_id,
        budget_id=budget_id,
        workshop=workshop,
        **extra_filters,
    )


def _get_current_step_from_referer(request, fallback_step):
    referer = request.META.get("HTTP_REFERER", "")
    if not referer:
        return fallback_step

    parsed = urlparse(referer)
    query_params = parse_qs(parsed.query)
    try:
        return int(query_params.get("step", [fallback_step])[0])
    except (TypeError, ValueError, IndexError):
        return fallback_step


def _budget_update_url(budget_id, step):
    return f"{reverse('budget:budget_update', kwargs={'pk': budget_id})}?step={step}"


def _step_redirect_response(request, budget):
    current_step = _get_current_step_from_referer(request, budget.current_step)
    response = HttpResponse()
    response["HX-Redirect"] = _budget_update_url(budget.id, current_step)
    return response


def _parse_duration_from_string(raw_duration):
    if not raw_duration:
        return timedelta()
    try:
        return DurationField.parse_duration(raw_duration) or timedelta()
    except (TypeError, ValueError):
        return timedelta()


def _get_budget_workshop_cost(budget, workshop):
    try:
        reference_date = budget.criado_em if budget.criado_em else timezone.now()
        return (
            WorkshopCost.objects.get(workshop=workshop, month=reference_date.month, year=reference_date.year),
            False,
        )
    except WorkshopCost.DoesNotExist:
        try:
            return (
                WorkshopCost.objects.get(workshop=workshop, month=timezone.now().month, year=timezone.now().year),
                False,
            )
        except WorkshopCost.DoesNotExist:
            return None, True


def _calculate_service_prices(duration, workshop_cost):
    duration_hours = Decimal(duration.total_seconds()) / Decimal(3600)

    if workshop_cost:
        min_hourly = workshop_cost.minimum_hourly_cost or Money(0, "BRL")
        hourly_val = workshop_cost.hourly_cost_value or Money(0, "BRL")
        return min_hourly * duration_hours, hourly_val * duration_hours

    return Money(0, "BRL"), Money(0, "BRL")


def _budget_item_row_template(item):
    is_local_product = item.is_local and (item.product_cost_price.amount > 0 or item.product_selling_price.amount > 0 or item.shipping.amount > 0)
    is_local_service = item.is_local and (item.service_cost_price.amount > 0 or item.service_selling_price.amount > 0 or item.duration)

    if item.product or is_local_product:
        return "budget/partials/items/item_product_row.html"
    if item.service or is_local_service:
        return "budget/partials/items/item_service_row.html"
    return "budget/partials/items/item_kit_row.html"


def _local_item_kind(item):
    is_product = item.product_cost_price.amount > 0 or item.product_selling_price.amount > 0
    return "product" if is_product else "service"


def reset_steps_after_step_4(budget):
    """
    Reseta completamente as etapas 5 e 6 quando a etapa 4 é modificada.
    Limpa todos os campos de precificação e força o usuário a reconfigurar.

    Campos resetados:
    - current_step: volta para 4
    - slider: volta para 0
    - discount_value: volta para 0.00
    """
    if budget.current_step > 4:
        budget.current_step = 4
        budget.slider = 0
        budget.discount_value = Money(0, "BRL")
        budget.status = BudgetStatus.WAITING_PRICING
        budget.save(update_fields=["current_step", "slider", "discount_value", "status"])
