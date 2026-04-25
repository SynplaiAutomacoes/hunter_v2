import logging
from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem, BudgetStatus
from apps.budget.fields import DurationField
from apps.workshops.models.workshop_costs import WorkshopCost

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


def _step_redirect_response(request, budget, fallback_step=None):
    base_step = fallback_step if fallback_step is not None else budget.current_step
    current_step = _get_current_step_from_referer(request, base_step)
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
    if budget and getattr(budget, "pk", None):
        return budget.get_frozen_pricing_context(), False

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
    - discount_percentage: volta para 0%
    - step5_calculation_viewed: volta para False
    """
    if budget.current_step > 4:
        budget.current_step = 4
        budget.slider = 0
        budget.discount_value = Money(0, "BRL")
        budget.discount_percentage = Decimal("0")
        budget.step5_calculation_viewed = False
        budget.status = BudgetStatus.WAITING_PRICING
        budget.save(update_fields=["current_step", "slider", "discount_value", "discount_percentage", "step5_calculation_viewed", "status"])
