from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

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


def _normalize_buckets_to_total(*, products_base: Decimal, services_base: Decimal, total_base: Decimal) -> tuple[Decimal, Decimal]:
    base_sum = products_base + services_base
    if total_base <= 0:
        return Decimal("0.00"), Decimal("0.00")

    if base_sum <= 0:
        return total_base, Decimal("0.00")

    if base_sum == total_base:
        return _quantize_money(products_base), _quantize_money(services_base)

    products_scaled = _quantize_money((products_base / base_sum) * total_base)
    services_scaled = _quantize_money(total_base - products_scaled)
    residual = _quantize_money(total_base - (products_scaled + services_scaled))
    if residual:
        services_scaled = _quantize_money(services_scaled + residual)
    return products_scaled, services_scaled


def compute_slider_allocation(*, products_base: Decimal, services_base: Decimal, slider: int) -> tuple[Decimal, Decimal]:
    slider_value = max(-100, min(100, int(slider)))
    if slider_value == 0:
        return _quantize_money(products_base), _quantize_money(services_base)

    if slider_value < 0:
        transfer = services_base * (Decimal(abs(slider_value)) / _HUNDRED)
        products_target = products_base + transfer
        services_target = services_base - transfer
    else:
        transfer = products_base * (Decimal(slider_value) / _HUNDRED)
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


def build_slider_allocation_for_workorder(*, workorder: WorkOrder) -> SliderAllocation:
    budget = workorder.budget
    slider_value = int(getattr(budget, "slider", 0) or 0)

    products_source = _to_decimal_money(workorder.total_products_value)
    services_source = _to_decimal_money(workorder.total_services_value)
    total_base = _to_decimal_money(budget.total_budget_value)

    products_base, services_base = _normalize_buckets_to_total(products_base=products_source, services_base=services_source, total_base=total_base)
    products_target, services_target = compute_slider_allocation(products_base=products_base, services_base=services_base, slider=slider_value)

    total_target = _quantize_money(products_target + services_target)
    total_residual = _quantize_money(total_base - total_target)
    if total_residual:
        services_target = _quantize_money(services_target + total_residual)

    return SliderAllocation(
        slider=slider_value,
        products_base=_quantize_money(products_base),
        services_base=_quantize_money(services_base),
        total_base=_quantize_money(total_base),
        products_target=_quantize_money(products_target),
        services_target=_quantize_money(services_target),
    )


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
