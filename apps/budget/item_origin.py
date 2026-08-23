from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

from django.utils.html import escape

from apps.budget.pricing import format_duration_display, money_div, zero_money

AVULSO_ORIGIN_LABEL = "Avulso"
KIT_ORIGIN_LABEL = "Kit"


def kit_origin_name(item: Any) -> str:
    kit = getattr(item, "kit", None)
    if kit is None:
        return ""
    return str(getattr(kit, "name", "") or "").strip()


def build_origin_badge(*, label: str, is_kit: bool = False, tooltip: str = "") -> str:
    tone = "badge-info badge-outline" if is_kit else "badge-outline"
    badge = f'<span class="badge {tone} whitespace-nowrap">{escape(label)}</span>'
    tip = str(tooltip or "").strip()
    if not is_kit or not tip:
        return badge
    escaped_tip = escape(tip)
    return (
        f'<span class="tooltip tooltip-bottom z-20 inline-flex cursor-help before:z-50 before:max-w-[16rem] before:whitespace-normal before:break-words before:text-xs" '
        f'data-tip="{escaped_tip}" tabindex="0">{badge}</span>'
    )


def origin_badge_for_item(*, item: Any) -> tuple[str, str, bool]:
    if getattr(item, "kit_id", None) or getattr(item, "kit", None):
        return KIT_ORIGIN_LABEL, build_origin_badge(label=KIT_ORIGIN_LABEL, is_kit=True, tooltip=kit_origin_name(item)), True
    return AVULSO_ORIGIN_LABEL, build_origin_badge(label=AVULSO_ORIGIN_LABEL), False


def _effective_kit_quantity(item: Any) -> int:
    return int(getattr(item, "quantity", 0) or 0)


def iter_kit_product_components(item: Any) -> list[Any]:
    return [override for override in item._iter_frozen_kit_product_overrides() if int(getattr(override, "quantity", 0) or 0) > 0]


def iter_kit_service_components(item: Any) -> list[Any]:
    return [override for override in item._iter_frozen_kit_service_overrides() if int(getattr(override, "quantity", 0) or 0) > 0]


def kit_component_winning_item_ids(items: list[Any]) -> tuple[dict[int, int], dict[int, int]]:
    """Return product_id/service_id -> budget item id using the kit-vs-kit winner rule."""
    from apps.budget.pricing import _is_better_service_source, _is_better_source, zero_money

    product_winners: dict[int, tuple[int, Any, int]] = {}
    service_winners: dict[int, tuple[timedelta, Any, int]] = {}

    for item in items:
        item_id = getattr(item, "pk", None)
        if item_id is None or not getattr(item, "kit_id", None):
            continue
        kit_quantity = _effective_kit_quantity(item)
        if kit_quantity <= 0:
            continue

        for override in iter_kit_product_components(item):
            product_id = getattr(override, "product_id", None)
            if product_id is None:
                continue
            quantity = int(getattr(override, "quantity", 0) or 0) * kit_quantity
            unit_price = getattr(override, "product_selling_price", None) or zero_money()
            shipping = (getattr(override, "shipping", None) or zero_money()) * kit_quantity
            total = (unit_price * quantity) + shipping
            current = product_winners.get(product_id)
            if current is None or _is_better_source(
                candidate_quantity=quantity,
                candidate_total=total,
                current_quantity=current[0],
                current_total=current[1],
            ):
                product_winners[product_id] = (quantity, total, item_id)

        for override in iter_kit_service_components(item):
            service_id = getattr(override, "service_id", None)
            if service_id is None:
                continue
            quantity = int(getattr(override, "quantity", 0) or 0) * kit_quantity
            unit_price = getattr(override, "service_selling_price", None) or zero_money()
            total = unit_price * quantity
            duration = getattr(override, "duration", None) or timedelta()
            duration = duration * quantity
            current = service_winners.get(service_id)
            if current is None or _is_better_service_source(
                candidate_duration=duration,
                candidate_total=total,
                current_duration=current[0],
                current_total=current[1],
            ):
                service_winners[service_id] = (duration, total, item_id)

    return (
        {product_id: winner[2] for product_id, winner in product_winners.items()},
        {service_id: winner[2] for service_id, winner in service_winners.items()},
    )


def build_kit_component_product_item(*, kit_item: Any, override: Any) -> SimpleNamespace | None:
    per_kit_quantity = int(getattr(override, "quantity", 0) or 0)
    kit_quantity = _effective_kit_quantity(kit_item)
    total_quantity = per_kit_quantity * kit_quantity
    if total_quantity <= 0:
        return None

    product = override.product
    unit_cost = getattr(override, "product_cost_price", None) or zero_money()
    unit_price = getattr(override, "product_selling_price", None) or zero_money()
    shipping_total = (getattr(override, "shipping", None) or zero_money()) * kit_quantity
    total_price = (unit_price * total_quantity) + shipping_total
    product_id = getattr(override, "product_id", None) or getattr(product, "pk", None)

    return SimpleNamespace(
        id=f"kit-{kit_item.pk}-p-{product_id}",
        pk=None,
        is_local=False,
        description=getattr(product, "name", "") or "",
        item_benefit_type=kit_item.item_benefit_type,
        product=product,
        product_id=product_id,
        is_customer_supplied=False,
        quantity=total_quantity,
        has_product_issues=False,
        product_issue_tooltip="",
        product_cost_price=unit_cost,
        product_selling_price=unit_price,
        display_product_selling_price=unit_price,
        shipping=shipping_total,
        display_total_price=total_price,
        total_price=total_price,
        show_kit_duplicate_warning=False,
        is_kit_component=True,
    )


def build_kit_component_service_item(*, kit_item: Any, override: Any) -> SimpleNamespace | None:
    per_kit_quantity = int(getattr(override, "quantity", 0) or 0)
    kit_quantity = _effective_kit_quantity(kit_item)
    total_quantity = per_kit_quantity * kit_quantity
    if total_quantity <= 0:
        return None

    service = override.service
    unit_cost = getattr(override, "service_cost_price", None) or zero_money()
    unit_price = getattr(override, "service_selling_price", None) or zero_money()
    duration = getattr(override, "duration", None)
    total_duration = (duration * total_quantity) if duration else None
    total_price = unit_price * total_quantity
    service_id = getattr(override, "service_id", None) or getattr(service, "pk", None)
    service_shipping = getattr(override, "service_shipping", None)
    if service_shipping is None:
        service_shipping = getattr(service, "shipping", None) or zero_money()
        service_shipping = service_shipping * kit_quantity

    return SimpleNamespace(
        id=f"kit-{kit_item.pk}-s-{service_id}",
        pk=None,
        is_local=False,
        description=getattr(service, "name", "") or "",
        item_benefit_type=kit_item.item_benefit_type,
        service=service,
        service_id=service_id,
        quantity=total_quantity,
        service_cost_price=unit_cost,
        service_selling_price=unit_price,
        display_service_selling_price=unit_price,
        service_shipping=service_shipping,
        duration=duration,
        duration_display=format_duration_display(total_duration or timedelta()),
        display_total_price=total_price,
        total_price=total_price,
        show_kit_duplicate_warning=False,
        is_kit_component=True,
    )


def build_kit_component_product_item_from_exploded(*, kit_item: Any, row: dict[str, Any]) -> SimpleNamespace:
    quantity = int(row.get("quantity") or 0)
    unit_cost = money_div(row.get("product_cost_price") or zero_money(), quantity) if quantity else zero_money()
    unit_price = row.get("unit_price") or zero_money()
    product_id = row.get("id")
    return SimpleNamespace(
        id=f"kit-{kit_item.pk}-p-{product_id}",
        pk=None,
        is_local=False,
        description=row.get("description") or "",
        item_benefit_type=row.get("item_benefit_type") or kit_item.item_benefit_type,
        product=SimpleNamespace(application=row.get("application") or "-", id=product_id),
        product_id=product_id,
        is_customer_supplied=bool(row.get("is_customer_supplied")),
        quantity=quantity,
        has_product_issues=False,
        product_issue_tooltip="",
        product_cost_price=unit_cost,
        product_selling_price=unit_price,
        display_product_selling_price=unit_price,
        shipping=row.get("shipping") or zero_money(),
        display_total_price=row.get("total_price") or zero_money(),
        total_price=row.get("total_price") or zero_money(),
        show_kit_duplicate_warning=False,
        is_kit_component=True,
    )


def build_kit_component_service_item_from_exploded(*, kit_item: Any, row: dict[str, Any]) -> SimpleNamespace:
    quantity = int(row.get("quantity") or 0)
    unit_cost = money_div(row.get("service_cost_price") or zero_money(), quantity) if quantity else zero_money()
    unit_price = row.get("unit_price") or zero_money()
    mechanic_cost = money_div(row.get("service_mechanic_cost_price") or zero_money(), quantity) if quantity else zero_money()
    service_id = row.get("id")
    return SimpleNamespace(
        id=f"kit-{kit_item.pk}-s-{service_id}",
        pk=None,
        is_local=False,
        description=row.get("description") or "",
        item_benefit_type=row.get("item_benefit_type") or kit_item.item_benefit_type,
        service=SimpleNamespace(id=service_id, is_third_party=False),
        service_id=service_id,
        quantity=quantity,
        service_cost_price=unit_cost,
        service_selling_price=unit_price,
        display_service_selling_price=unit_price,
        service_shipping=row.get("shipping") or zero_money(),
        duration=None,
        duration_display=row.get("duration_display") or "00h 00m",
        display_total_price=row.get("total_price") or zero_money(),
        total_price=row.get("total_price") or zero_money(),
        mechanic_cost=mechanic_cost,
        show_kit_duplicate_warning=False,
        is_kit_component=True,
    )
