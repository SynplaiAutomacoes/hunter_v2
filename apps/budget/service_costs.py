from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from djmoney.money import Money


def calculate_mechanic_service_cost(*, budget: Any, duration: timedelta | None, quantity: int = 1, fallback_cost: Money | None = None) -> Money:
    duration_hours = Decimal((duration or timedelta()).total_seconds()) / Decimal(3600)
    mechanic_hour_cost = getattr(budget, "mechanic_hour_cost_value", Money(0, "BRL")) or Money(0, "BRL")
    if mechanic_hour_cost.amount <= 0 and fallback_cost is not None:
        return fallback_cost

    amount = (mechanic_hour_cost * duration_hours * Decimal(max(0, quantity))).amount.quantize(Decimal("0.01"), ROUND_HALF_UP)
    return Money(amount, "BRL")
