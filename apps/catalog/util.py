from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Case, IntegerField, QuerySet, Value, When

from django.utils import timezone
from djmoney.money import Money

from apps.catalog.models.kits import Kit, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.core.infrastructure.search import apply_text_search
from apps.workshops.models.workshop_costs import WorkshopCost


def get_current_workshop_cost(workshop):
    today = timezone.localdate()
    try:
        cost = WorkshopCost.objects.get(workshop=workshop, month=today.month, year=today.year)
        return cost, False
    except WorkshopCost.DoesNotExist:
        return None, True


def calculate_catalog_service_prices(duration, workshop_cost):
    """Calcula custo e venda baseados na duração (timedelta) e WorkshopCost."""
    if not duration:
        return Money(0, "BRL"), Money(0, "BRL")

    duration_hours = Decimal(duration.total_seconds()) / Decimal(3600)

    if workshop_cost:
        min_hourly = workshop_cost.minimum_hourly_cost or Money(0, "BRL")
        hourly_val = workshop_cost.hourly_cost_value or Money(0, "BRL")

        cost = min_hourly * duration_hours
        sale = hourly_val * duration_hours
        return cost, sale

    return Money(0, "BRL"), Money(0, "BRL")


def recalculate_kit_totals(kit: Kit) -> Kit:
    product_total = Money(0, "BRL")
    for kit_product in KitProduct.objects.filter(kit=kit).select_related("product"):
        product_total += (kit_product.product.selling_price or Money(0, "BRL")) * kit_product.quantity

    service_total = Money(0, "BRL")
    services_total_duration = timedelta()
    for item in KitService.objects.filter(kit=kit).select_related("service"):
        unit_sell = item.resolved_duration_selling_price if kit.service_pricing_mode == Kit.ServicePricingMode.BY_DURATION else item.resolved_selling_price
        service_total += unit_sell * item.quantity
        services_total_duration += (item.duration or timedelta()) * item.quantity

    kit.total_price = product_total + service_total
    kit.total_duration = services_total_duration
    kit.save(update_fields=["total_price", "total_duration", "service_pricing_mode", "atualizado_em"])
    return kit


def build_product_kits_assignment_context(
    *,
    workshop,
    product: Product,
    query: str = "",
    page: str | int = "1",
    selected_kit_ids: list[int] | list[str] | None = None,
) -> dict[str, object]:
    cleaned_query = str(query or "").strip()
    normalized_selected_ids = _normalize_selected_kit_ids(selected_kit_ids or [])

    assigned_kit_ids = set(KitProduct.objects.filter(kit__workshop=workshop, product=product).values_list("kit_id", flat=True))
    pending_selected_kit_ids = [kit_id for kit_id in normalized_selected_ids if kit_id not in assigned_kit_ids]

    kits_queryset: QuerySet[Kit] = Kit.objects.filter(workshop=workshop)
    if cleaned_query:
        kits_queryset = apply_text_search(kits_queryset, search_value=cleaned_query, lookups=("name",))

    if assigned_kit_ids:
        kits_queryset = kits_queryset.annotate(
            assignment_order=Case(
                When(id__in=assigned_kit_ids, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        ).order_by("-assignment_order", "name")
    else:
        kits_queryset = kits_queryset.order_by("name")

    paginator = Paginator(kits_queryset, 10)
    page_obj = paginator.get_page(page)

    for kit in page_obj.object_list:
        kit.is_product_assigned = kit.id in assigned_kit_ids
        kit.is_pending_product_assignment = kit.id in pending_selected_kit_ids

    return {
        "kits_page_obj": page_obj,
        "kits_query": cleaned_query,
        "assigned_kit_ids": sorted(assigned_kit_ids),
        "pending_selected_kit_ids": pending_selected_kit_ids,
        "pending_selected_kit_ids_json": pending_selected_kit_ids,
    }


def _normalize_selected_kit_ids(selected_kit_ids: list[int] | list[str]) -> list[int]:
    normalized_ids: list[int] = []
    seen_ids: set[int] = set()

    for raw_id in selected_kit_ids:
        try:
            kit_id = int(str(raw_id).strip())
        except (TypeError, ValueError):
            continue

        if kit_id <= 0 or kit_id in seen_ids:
            continue

        normalized_ids.append(kit_id)
        seen_ids.add(kit_id)

    return normalized_ids
