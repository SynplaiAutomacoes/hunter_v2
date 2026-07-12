import logging
import json
from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem, BudgetStatus
from apps.budget.fields import DurationField
from apps.workorder.models import WorkOrder
from apps.workshops.models.workshop_costs import WorkshopCost

logger = logging.getLogger(__name__)
LOCKED_BUDGET_EDIT_MESSAGE = "Reabra o orçamento antes de editar qualquer campo."
CONCURRENT_BUDGET_LOCK_MESSAGE = "Outro usuário está editando este orçamento neste momento. Tente novamente em instantes."


def _get_budget_for_workshop(workshop, budget_id):
    return get_object_or_404(Budget, id=budget_id, workshop=workshop)


def _get_budget_for_summary(workshop, budget_id):
    from django.db.models import Count, Q

    from apps.core.infrastructure.kit_prefetch import budget_items_with_kit_prefetch

    return get_object_or_404(
        Budget.objects.annotate(
            annotated_warranty_items_count=Count("items", filter=Q(items__item_benefit_type="warranty"), distinct=True),
            annotated_courtesy_items_count=Count("items", filter=Q(items__item_benefit_type="courtesy"), distinct=True),
        ).prefetch_related(budget_items_with_kit_prefetch(with_kit_tree=False)),
        id=budget_id,
        workshop=workshop,
    )


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


def _build_locked_budget_response(request, budget, *, fallback_step=None, status_code: int = 409):
    response = _step_redirect_response(request, budget, fallback_step=fallback_step)
    response.status_code = status_code
    response["HX-Trigger"] = json.dumps({"showToast": {"message": LOCKED_BUDGET_EDIT_MESSAGE, "type": "warning"}})
    return response


def _is_budget_edit_locked(budget: Budget) -> bool:
    return bool(getattr(budget, "is_status_locked", False))


def _parse_duration_from_string(raw_duration):
    if not raw_duration:
        return timedelta()
    try:
        return DurationField.parse_duration(raw_duration) or timedelta()
    except (TypeError, ValueError):
        return timedelta()


def _get_budget_workshop_cost(budget, workshop):
    if budget and getattr(budget, "pk", None):
        workshop_cost = budget.get_frozen_pricing_context()
        return workshop_cost, not _has_service_duration_pricing(workshop_cost)

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


def _has_service_duration_pricing(workshop_cost) -> bool:
    if not workshop_cost:
        return False

    hourly_value = workshop_cost.hourly_cost_value or Money(0, "BRL")
    return hourly_value.amount > 0


def _calculate_service_prices(duration, workshop_cost):
    duration_hours = Decimal(duration.total_seconds()) / Decimal(3600)

    if workshop_cost and _has_service_duration_pricing(workshop_cost):
        min_hourly = workshop_cost.minimum_hourly_cost or Money(0, "BRL")
        hourly_val = workshop_cost.hourly_cost_value or Money(0, "BRL")
        return min_hourly * duration_hours, hourly_val * duration_hours

    return Money(0, "BRL"), Money(0, "BRL")


def _budget_item_row_template(item):
    if item.local_item_type == "product":
        return "budget/partials/items/item_product_row.html"
    if item.local_item_type == "service":
        return "budget/partials/items/item_service_row.html"

    is_local_product = item.is_local and (item.product_cost_price.amount > 0 or item.product_selling_price.amount > 0 or item.shipping.amount > 0)
    is_local_service = item.is_local and (item.service_cost_price.amount > 0 or item.service_selling_price.amount > 0 or item.duration)

    if item.product or is_local_product:
        return "budget/partials/items/item_product_row.html"
    if item.service or is_local_service:
        return "budget/partials/items/item_service_row.html"
    return "budget/partials/items/item_kit_row.html"


def _local_item_kind(item):
    if item.local_item_type in {"product", "service"}:
        return item.local_item_type
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
    - pricing_reference_month/year: volta para None (força recongelamento com valores atuais)
    - pricing_productive_salary_total: volta para None
    - pricing_working_hours_per_month: volta para None
    - pricing_minimum_hourly_cost: volta para None
    - pricing_hourly_cost_value: volta para None
    - pricing_profitability_multiplier: volta para None
    """
    if budget.current_step > 4:
        budget.current_step = 4
        budget.slider = 0
        budget.discount_value = Money(0, "BRL")
        budget.discount_percentage = Decimal("0")
        budget.step5_calculation_viewed = False
        budget.status = BudgetStatus.WAITING_PRICING
        # Limpa o snapshot de precificação congelado para forçar recongelamento
        # com os valores atuais da oficina na próxima vez que a etapa 5 for carregada.
        budget.pricing_reference_month = None
        budget.pricing_reference_year = None
        budget.pricing_productive_salary_total = None
        budget.pricing_working_hours_per_month = None
        budget.pricing_minimum_hourly_cost = None
        budget.pricing_hourly_cost_value = None
        budget.pricing_profitability_multiplier = None
        budget.save(
            update_fields=[
                "current_step",
                "slider",
                "discount_value",
                "discount_percentage",
                "step5_calculation_viewed",
                "status",
                "pricing_reference_month",
                "pricing_reference_year",
                "pricing_productive_salary_total",
                "pricing_productive_salary_total_currency",
                "pricing_working_hours_per_month",
                "pricing_minimum_hourly_cost",
                "pricing_minimum_hourly_cost_currency",
                "pricing_hourly_cost_value",
                "pricing_hourly_cost_value_currency",
                "pricing_profitability_multiplier",
            ]
        )


def sync_linked_workorder_from_budget(budget: Budget) -> None:
    workorder = WorkOrder.objects.filter(budget=budget).order_by("id").first()
    if workorder is None:
        return
    workorder.sync_from_budget()


def _check_concurrent_budget_lock(request, budget: Budget, check_session: bool = True) -> bool:
    from apps.core.domain.services.editing_lock_service import get_lock_info
    lock_info = get_lock_info(budget)
    if lock_info is None:
        return True
    if check_session and lock_info.get("locked_by_session") == request.session.session_key:
        return True
    return False


def _build_concurrent_budget_lock_response(request, budget: Budget, *, status_code: int = 409) -> HttpResponse:
    from apps.core.domain.services.editing_lock_service import get_lock_info
    lock_info = get_lock_info(budget)
    user_name = lock_info["locked_by"] if lock_info else "outro usuário"
    message = f"Outro usuário ({user_name}) está editando este orçamento neste momento. Tente novamente em instantes."
    response = JsonResponse({"ok": False, "error": message}, status=status_code)
    response["HX-Trigger"] = json.dumps({"showToast": {"message": message, "type": "warning"}})
    return response
