from __future__ import annotations

from copy import copy
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace
from typing import Any

from djmoney.money import Money

from apps.workorder.models import WorkOrder, WorkOrderItem

LineOverrides = dict[str, Any]

MONEY_FIELDS = (
    "product_selling_price",
    "product_cost_price",
    "shipping",
    "service_selling_price",
    "service_cost_price",
)
ITEM_OVERRIDE_FIELDS = (
    "description",
    "quantity",
    "is_customer_supplied",
    "product_selling_price",
    "product_cost_price",
    "shipping",
    "service_selling_price",
    "service_cost_price",
    "duration",
    "item_benefit_type",
)


def empty_line_overrides() -> LineOverrides:
    return {}


def normalize_line_overrides(raw: object) -> LineOverrides:
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items() if isinstance(value, dict)}


def item_override_key(item_id: int) -> str:
    return str(int(item_id))


def kit_component_override_key(*, item_id: int, component_type: str, component_id: int) -> str:
    return f"{int(item_id)}:{component_type}:{int(component_id)}"


def _quantize_money_amount(value: object) -> Decimal:
    amount = Decimal(str(getattr(value, "amount", value) or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return max(amount, Decimal("0.00"))


def money_to_override_value(value: object) -> str:
    return str(_quantize_money_amount(value))


def money_from_override_value(value: object) -> Money:
    return Money(_quantize_money_amount(value), "BRL")


def duration_to_override_value(value: object) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, timedelta):
        return str(int(value.total_seconds()))
    raw = str(value).strip()
    return raw or None


def duration_from_override_value(value: object) -> timedelta | None:
    if value in (None, ""):
        return None
    if isinstance(value, timedelta):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
        return timedelta(seconds=int(raw))
    parts = raw.split(":")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        hours, minutes, seconds = (int(part) for part in parts)
        return timedelta(hours=hours, minutes=minutes, seconds=seconds)
    return None


def serialize_item_override_from_cleaned_data(cleaned_data: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field_name in ITEM_OVERRIDE_FIELDS:
        if field_name not in cleaned_data:
            continue
        value = cleaned_data.get(field_name)
        if field_name in MONEY_FIELDS:
            payload[field_name] = money_to_override_value(value)
        elif field_name == "duration":
            payload[field_name] = duration_to_override_value(value)
        elif field_name == "quantity":
            payload[field_name] = int(value or 0)
        elif field_name == "is_customer_supplied":
            payload[field_name] = bool(value)
        else:
            payload[field_name] = value
    return payload


def serialize_kit_product_override_from_cleaned_data(cleaned_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "quantity": int(cleaned_data.get("quantity") or 0),
        "cost": money_to_override_value(cleaned_data.get("cost")),
        "price": money_to_override_value(cleaned_data.get("price")),
        "shipping": money_to_override_value(cleaned_data.get("shipping")),
    }


def serialize_kit_service_override_from_cleaned_data(cleaned_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "quantity": int(cleaned_data.get("quantity") or 0),
        "cost": money_to_override_value(cleaned_data.get("cost")),
        "price": money_to_override_value(cleaned_data.get("price")),
        "duration": duration_to_override_value(cleaned_data.get("duration")),
    }


def upsert_item_override(*, line_overrides: LineOverrides, item_id: int, override: dict[str, Any]) -> LineOverrides:
    updated = dict(normalize_line_overrides(line_overrides))
    updated[item_override_key(item_id)] = dict(override)
    return updated


def upsert_kit_component_override(
    *,
    line_overrides: LineOverrides,
    item_id: int,
    component_type: str,
    component_id: int,
    override: dict[str, Any],
) -> LineOverrides:
    updated = dict(normalize_line_overrides(line_overrides))
    updated[kit_component_override_key(item_id=item_id, component_type=component_type, component_id=component_id)] = dict(override)
    return updated


def get_item_override(*, line_overrides: LineOverrides, item_id: int) -> dict[str, Any] | None:
    value = normalize_line_overrides(line_overrides).get(item_override_key(item_id))
    return dict(value) if isinstance(value, dict) else None


def get_kit_component_override(
    *,
    line_overrides: LineOverrides,
    item_id: int,
    component_type: str,
    component_id: int,
) -> dict[str, Any] | None:
    value = normalize_line_overrides(line_overrides).get(
        kit_component_override_key(item_id=item_id, component_type=component_type, component_id=component_id)
    )
    return dict(value) if isinstance(value, dict) else None


def build_item_form_initial(*, item: WorkOrderItem, line_overrides: LineOverrides) -> dict[str, Any]:
    override = get_item_override(line_overrides=line_overrides, item_id=item.pk) or {}
    initial: dict[str, Any] = {}
    for field_name in ITEM_OVERRIDE_FIELDS:
        if field_name not in override:
            continue
        value = override[field_name]
        if field_name in MONEY_FIELDS:
            initial[field_name] = money_from_override_value(value)
        elif field_name == "duration":
            initial[field_name] = duration_from_override_value(value)
        else:
            initial[field_name] = value
    return initial


def build_kit_product_form_initial(
    *,
    item: WorkOrderItem,
    component_id: int,
    line_overrides: LineOverrides,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    override = get_kit_component_override(
        line_overrides=line_overrides,
        item_id=item.pk,
        component_type="product",
        component_id=component_id,
    )
    if not override:
        return fallback
    return {
        "quantity": int(override.get("quantity") or 0),
        "cost": money_from_override_value(override.get("cost")),
        "price": money_from_override_value(override.get("price")),
        "shipping": money_from_override_value(override.get("shipping")),
    }


def build_kit_service_form_initial(
    *,
    item: WorkOrderItem,
    component_id: int,
    line_overrides: LineOverrides,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    override = get_kit_component_override(
        line_overrides=line_overrides,
        item_id=item.pk,
        component_type="service",
        component_id=component_id,
    )
    if not override:
        return fallback
    return {
        "quantity": int(override.get("quantity") or 0),
        "cost": money_from_override_value(override.get("cost")),
        "price": money_from_override_value(override.get("price")),
        "duration": duration_from_override_value(override.get("duration")),
    }


def _apply_item_override_in_memory(*, item: WorkOrderItem, override: dict[str, Any]) -> None:
    if "description" in override:
        item.description = str(override.get("description") or "")
    if "quantity" in override:
        item.quantity = int(override.get("quantity") or 0)
    if "is_customer_supplied" in override:
        item.is_customer_supplied = bool(override.get("is_customer_supplied"))
    if "item_benefit_type" in override and override.get("item_benefit_type") not in (None, ""):
        item.item_benefit_type = str(override["item_benefit_type"])
    for field_name in MONEY_FIELDS:
        if field_name in override:
            setattr(item, field_name, money_from_override_value(override.get(field_name)))
    if "duration" in override:
        item.duration = duration_from_override_value(override.get("duration"))


def _merge_kit_overrides_cache(*, item: WorkOrderItem, line_overrides: LineOverrides) -> None:
    if not item.kit_id:
        return

    base_overrides = list(item._cached_kit_overrides())
    merged_by_key: dict[str, Any] = {}
    for override in base_overrides:
        if getattr(override, "product_id", None):
            merged_by_key[f"product:{override.product_id}"] = override
        if getattr(override, "service_id", None):
            merged_by_key[f"service:{override.service_id}"] = override

    normalized = normalize_line_overrides(line_overrides)
    prefix = f"{item.pk}:"
    for key, payload in normalized.items():
        if not key.startswith(prefix) or not isinstance(payload, dict):
            continue
        parts = key.split(":")
        if len(parts) != 3:
            continue
        _item_id, component_type, component_id_raw = parts
        if component_type not in {"product", "service"} or not component_id_raw.isdigit():
            continue
        component_id = int(component_id_raw)
        existing = merged_by_key.get(f"{component_type}:{component_id}")
        if component_type == "product":
            ephemeral = SimpleNamespace(
                product_id=component_id,
                service_id=None,
                product=getattr(existing, "product", None),
                service=None,
                quantity=int(payload.get("quantity") or 0),
                product_cost_price=money_from_override_value(payload.get("cost")),
                product_selling_price=money_from_override_value(payload.get("price")),
                shipping=money_from_override_value(payload.get("shipping")),
                service_cost_price=Money(0, "BRL"),
                service_selling_price=Money(0, "BRL"),
                duration=None,
            )
            if ephemeral.product is None:
                for kit_product in item._iter_kit_products():
                    if kit_product.product_id == component_id:
                        ephemeral.product = kit_product.product
                        break
            merged_by_key[f"product:{component_id}"] = ephemeral
        else:
            ephemeral = SimpleNamespace(
                product_id=None,
                service_id=component_id,
                product=None,
                service=getattr(existing, "service", None),
                quantity=int(payload.get("quantity") or 0),
                product_cost_price=Money(0, "BRL"),
                product_selling_price=Money(0, "BRL"),
                shipping=Money(0, "BRL"),
                service_cost_price=money_from_override_value(payload.get("cost")),
                service_selling_price=money_from_override_value(payload.get("price")),
                duration=duration_from_override_value(payload.get("duration")),
            )
            if ephemeral.service is None:
                for kit_service in item._iter_kit_services():
                    if kit_service.service_id == component_id:
                        ephemeral.service = kit_service.service
                        break
            merged_by_key[f"service:{component_id}"] = ephemeral

    setattr(item, "_kit_overrides_list_cache", list(merged_by_key.values()))
    if hasattr(item, "_kit_override_maps_cache"):
        delattr(item, "_kit_override_maps_cache")
    prefetched = getattr(item, "_prefetched_objects_cache", None)
    if isinstance(prefetched, dict) and "kit_overrides" in prefetched:
        prefetched["kit_overrides"] = list(merged_by_key.values())


def apply_line_overrides_to_workorder(*, workorder: WorkOrder, line_overrides: LineOverrides | None) -> WorkOrder:
    """Mutate workorder items in memory so emission pricing/payload uses overrides without DB writes."""
    normalized = normalize_line_overrides(line_overrides)
    if not normalized:
        return workorder

    items = list(workorder._iter_items())
    for item in items:
        item_override = get_item_override(line_overrides=normalized, item_id=item.pk)
        if item_override:
            _apply_item_override_in_memory(item=item, override=item_override)
        _merge_kit_overrides_cache(item=item, line_overrides=normalized)

    # Keep the same in-memory instances for subsequent `_iter_items()` / pricing calls.
    prefetched = getattr(workorder, "_prefetched_objects_cache", None)
    if not isinstance(prefetched, dict):
        prefetched = {}
        setattr(workorder, "_prefetched_objects_cache", prefetched)
    prefetched["items"] = items
    return workorder


def resolve_request_line_overrides(*sources: object) -> LineOverrides:
    merged: LineOverrides = {}
    for source in sources:
        if source is None:
            continue
        if isinstance(source, dict):
            merged.update(normalize_line_overrides(source))
            continue
        merged.update(normalize_line_overrides(getattr(source, "line_overrides", None)))
    return merged


def copy_line_overrides(line_overrides: LineOverrides | None) -> LineOverrides:
    return {key: copy(value) for key, value in normalize_line_overrides(line_overrides).items()}
