from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

from apps.budget.pricing import PricingSnapshot, build_pricing_snapshot, money_from_decimal, resolve_discount_fields, zero_money
from apps.workorder.models import WorkOrder


_HUNDRED = Decimal("100")
_MONEY = Decimal("0.01")


def _to_decimal_money(value: object) -> Decimal:
    if hasattr(value, "amount"):
        return Decimal(str(getattr(value, "amount")))
    return Decimal(str(value or 0))


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class SliderAllocation:
    slider: int
    products_base: Decimal
    services_base: Decimal
    total_base: Decimal
    products_target: Decimal
    services_target: Decimal


def compute_slider_allocation(*, products_base: Decimal, services_base: Decimal, slider: int) -> tuple[Decimal, Decimal]:
    slider_value = max(-100, min(100, int(slider)))
    if slider_value == 0:
        return _quantize_money(products_base), _quantize_money(services_base)

    if slider_value > 0:
        transfer = products_base * (Decimal(slider_value) / _HUNDRED)
        products_target = products_base + transfer
        services_target = services_base - transfer
    else:
        transfer = services_base * (Decimal(abs(slider_value)) / _HUNDRED)
        products_target = products_base - transfer
        services_target = services_base + transfer

    products_target = _quantize_money(products_target)
    services_target = _quantize_money(services_target)

    total_base = _quantize_money(products_base + services_base)
    residual = _quantize_money(total_base - (products_target + services_target))
    if residual:
        services_target = _quantize_money(services_target + residual)

    if products_target < Decimal("0.00"):
        services_target = _quantize_money(services_target + products_target)
        products_target = Decimal("0.00")
    if services_target < Decimal("0.00"):
        products_target = _quantize_money(products_target + services_target)
        services_target = Decimal("0.00")

    return products_target, services_target


def resolve_slider_value_for_workorder(
    *,
    workorder: WorkOrder,
    persisted_slider: int | None = None,
    slider_override: int | None = None,
) -> int:
    if slider_override is not None:
        return max(-100, min(100, int(slider_override)))

    if persisted_slider is not None:
        return max(-100, min(100, int(persisted_slider)))

    budget = getattr(workorder, "budget", None)
    return max(-100, min(100, int(getattr(budget, "slider", 0) or 0)))


def build_emission_pricing_snapshot_for_workorder(
    *,
    workorder: WorkOrder,
    persisted_slider: int | None = None,
    slider_override: int | None = None,
) -> PricingSnapshot:
    slider_value = resolve_slider_value_for_workorder(
        workorder=workorder,
        persisted_slider=persisted_slider,
        slider_override=slider_override,
    )
    base_snapshot = build_pricing_snapshot(
        items=list(workorder._iter_items()),
        slider=0,
        discount_value=workorder.discount_value,
        discount_percentage=workorder.discount_percentage,
        discount_type=workorder.discount_type,
        labor_cost_value=workorder.total_labor_cost_value,
    )

    if slider_value == 0:
        return base_snapshot

    adjusted_snapshot = deepcopy(base_snapshot)
    products_target, services_target = compute_slider_allocation(
        products_base=_to_decimal_money(base_snapshot.total_products_value),
        services_base=_to_decimal_money(base_snapshot.total_services_value),
        slider=slider_value,
    )

    product_line_totals = distribute_total_proportionally(
        base_values=[_to_decimal_money(line.raw_total) for line in adjusted_snapshot.product_lines],
        target_total=products_target,
    )
    for line, line_total in zip(adjusted_snapshot.product_lines, product_line_totals, strict=False):
        line.shipping = zero_money()
        line.adjusted_total = money_from_decimal(line_total)

    service_line_totals = distribute_total_proportionally(
        base_values=[_to_decimal_money(line.raw_total) for line in adjusted_snapshot.service_lines],
        target_total=services_target,
    )
    for line, line_total in zip(adjusted_snapshot.service_lines, service_line_totals, strict=False):
        line.adjusted_total = money_from_decimal(line_total)

    adjusted_snapshot.total_products_by_slider = money_from_decimal(products_target)
    adjusted_snapshot.total_services_by_slider = money_from_decimal(services_target)
    adjusted_snapshot.total_third_party_services_selling = sum((line.adjusted_total for line in adjusted_snapshot.service_lines if line.third_party), zero_money())
    adjusted_snapshot.total_labor_by_slider = sum((line.adjusted_total for line in adjusted_snapshot.service_lines if not line.third_party), zero_money())
    adjusted_snapshot.total_base_value = money_from_decimal(products_target + services_target)
    resolved_discount, _ = resolve_discount_fields(
        total_base_value=adjusted_snapshot.total_base_value,
        discount_value=workorder.discount_value,
        discount_percentage=workorder.discount_percentage,
    )
    adjusted_snapshot.total_budget_value = adjusted_snapshot.total_base_value - resolved_discount

    return adjusted_snapshot


def build_slider_allocation_for_workorder(
    *,
    workorder: WorkOrder,
    persisted_slider: int | None = None,
    slider_override: int | None = None,
) -> SliderAllocation:
    slider_value = resolve_slider_value_for_workorder(
        workorder=workorder,
        persisted_slider=persisted_slider,
        slider_override=slider_override,
    )
    snapshot = build_emission_pricing_snapshot_for_workorder(
        workorder=workorder,
        persisted_slider=persisted_slider,
        slider_override=slider_override,
    )

    products_base = _quantize_money(_to_decimal_money(snapshot.total_products_value))
    services_base = _quantize_money(_to_decimal_money(snapshot.total_services_value))
    products_target = _quantize_money(_to_decimal_money(snapshot.total_products_by_slider))
    services_target = _quantize_money(_to_decimal_money(snapshot.total_services_by_slider))
    total_base = _quantize_money(products_target + services_target)

    return SliderAllocation(
        slider=slider_value,
        products_base=products_base,
        services_base=services_base,
        total_base=total_base,
        products_target=products_target,
        services_target=services_target,
    )


def build_nfse_service_preview_rows(
    *,
    workorder: WorkOrder,
    persisted_slider: int | None = None,
    slider_override: int | None = None,
) -> list[dict[str, Any]]:
    snapshot = build_emission_pricing_snapshot_for_workorder(
        workorder=workorder,
        persisted_slider=persisted_slider,
        slider_override=slider_override,
    )

    return [
        {
            "description": line.description,
            "quantity": line.quantity,
            "unit_value": line.adjusted_unit_price,
            "total_value": line.total_price,
        }
        for line in snapshot.service_lines
    ]


def distribute_total_proportionally(*, base_values: Iterable[Decimal], target_total: Decimal) -> list[Decimal]:
    bases = [_quantize_money(value) for value in base_values]
    if not bases:
        return []

    target = _quantize_money(target_total)
    base_sum = _quantize_money(sum(bases, Decimal("0.00")))

    if target <= 0:
        return [Decimal("0.00") for _ in bases]
    if base_sum <= 0:
        raise ValueError("Nao e possivel distribuir total sem base proporcional.")

    allocated: list[Decimal] = []
    running_total = Decimal("0.00")
    last_index = len(bases) - 1

    for index, base in enumerate(bases):
        if index == last_index:
            line_total = _quantize_money(target - running_total)
        else:
            line_total = _quantize_money((target * base) / base_sum)
            running_total = _quantize_money(running_total + line_total)

        if line_total < Decimal("0.00"):
            line_total = Decimal("0.00")
        allocated.append(line_total)

    residual = _quantize_money(target - sum(allocated, Decimal("0.00")))
    if residual:
        allocated[-1] = _quantize_money(allocated[-1] + residual)

    return allocated
