from __future__ import annotations

from typing import Any

from djmoney.money import Money

from apps.budget.pricing import zero_money


def _money_or_zero(value: Money | None) -> Money:
    if value is None:
        return zero_money()
    if isinstance(value, Money):
        return value
    return Money(value, "BRL")


def service_line_display_total(*, cost_total: Money, sale_total: Money, item: Any) -> Money:
    cost_total = _money_or_zero(cost_total)
    sale_total = _money_or_zero(sale_total)
    quantity = int(getattr(item, "quantity", 0) or 0)
    if quantity <= 0:
        return zero_money()
    benefit_type = str(getattr(item, "item_benefit_type", "normal") or "normal")
    if benefit_type not in ("normal", ""):
        return zero_money()
    return cost_total + sale_total
