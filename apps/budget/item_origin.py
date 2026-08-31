from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

from django.urls import reverse
from django.utils.html import escape

from apps.budget.pricing import format_duration_display, money_div, zero_money

AVULSO_ORIGIN_LABEL = "Avulso"
KIT_ORIGIN_LABEL = "Kit"


def kit_origin_name(item: Any) -> str:
    kit = getattr(item, "kit", None)
    if kit is None:
        return ""
    return str(getattr(kit, "name", "") or "").strip()


def kit_origin_id(item: Any) -> int | None:
    kit_id = getattr(item, "kit_id", None)
    if kit_id:
        return int(kit_id)
    kit = getattr(item, "kit", None)
    kit_pk = getattr(kit, "pk", None) if kit is not None else None
    if kit_pk:
        return int(kit_pk)
    return None


def kit_origin_url(item: Any) -> str:
    kit_id = kit_origin_id(item)
    if kit_id is None:
        return ""
    return reverse("catalog:kits_update", kwargs={"pk": kit_id})


def build_origin_badge(*, label: str, is_kit: bool = False, tooltip: str = "", href: str = "") -> str:
    tone = "badge-info badge-outline" if is_kit else "badge-outline"
    badge = f'<span class="badge {tone} whitespace-nowrap">{escape(label)}</span>'
    tip = str(tooltip or "").strip()
    url = str(href or "").strip()
    if not is_kit:
        return badge

    classes = ["inline-flex"]
    if tip:
        classes.append("tooltip tooltip-bottom z-20 before:z-50 before:max-w-[16rem] before:whitespace-normal before:break-words before:text-xs")
    if url:
        classes.append("cursor-pointer hover:opacity-80")
        attrs = f'class="{" ".join(classes)}" href="{escape(url)}"'
        if tip:
            attrs += f' data-tip="{escape(tip)}"'
        return f"<a {attrs}>{badge}</a>"
    if not tip:
        return badge
    return (
        f'<span class="tooltip tooltip-bottom z-20 inline-flex cursor-help before:z-50 before:max-w-[16rem] before:whitespace-normal before:break-words before:text-xs" '
        f'data-tip="{escape(tip)}" tabindex="0">{badge}</span>'
    )


def origin_badge_for_item(*, item: Any) -> tuple[str, str, bool]:
    if getattr(item, "kit_id", None) or getattr(item, "kit", None):
        return (
            KIT_ORIGIN_LABEL,
            build_origin_badge(
                label=KIT_ORIGIN_LABEL,
                is_kit=True,
                tooltip=kit_origin_name(item),
                href=kit_origin_url(item),
            ),
            True,
        )
    return AVULSO_ORIGIN_LABEL, build_origin_badge(label=AVULSO_ORIGIN_LABEL), False


def _effective_kit_quantity(item: Any) -> int:
    return int(getattr(item, "quantity", 0) or 0)


def iter_kit_product_components(item: Any) -> list[Any]:
    frozen = list(item._iter_frozen_kit_product_overrides())
    if frozen:
        return frozen

    product_overrides, _service_overrides = item._get_kit_override_maps()
    components: list[Any] = []
    for kit_product in item._iter_kit_products():
        override = product_overrides.get(kit_product.product_id)
        if override is not None:
            components.append(override)
            continue
        product = kit_product.product
        components.append(
            SimpleNamespace(
                product=product,
                product_id=kit_product.product_id,
                quantity=kit_product.quantity,
                product_cost_price=getattr(product, "cost_price", zero_money()),
                product_selling_price=getattr(product, "selling_price", zero_money()),
                shipping=zero_money(),
            )
        )
    return components


def iter_kit_service_components(item: Any) -> list[Any]:
    frozen = list(item._iter_frozen_kit_service_overrides())
    if frozen:
        return [
            override
            for override in frozen
            if int(getattr(override, "quantity", 0) or 0) > 0 and not getattr(override, "excluded_from_composition", False)
        ]

    _product_overrides, service_overrides = item._get_kit_override_maps()
    components: list[Any] = []
    for kit_service in item._iter_kit_services():
        override = service_overrides.get(kit_service.service_id)
        if override is not None:
            if int(getattr(override, "quantity", 0) or 0) <= 0 or getattr(override, "excluded_from_composition", False):
                continue
            components.append(override)
            continue
        service = kit_service.service
        components.append(
            SimpleNamespace(
                service=service,
                service_id=kit_service.service_id,
                quantity=kit_service.quantity,
                service_cost_price=getattr(service, "suggested_cost", None) or zero_money(),
                service_selling_price=getattr(kit_service, "resolved_selling_price", None) or getattr(service, "selling_price", zero_money()),
                duration=getattr(kit_service, "duration", None) or getattr(service, "duration", None),
                excluded_from_composition=False,
            )
        )
    return components


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
    if getattr(override, "excluded_from_composition", False):
        return None
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
        service=SimpleNamespace(id=service_id, is_third_party=bool(row.get("is_third_party", False))),
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
