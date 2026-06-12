from __future__ import annotations

from decimal import Decimal

from djmoney.money import Money

from apps.budget.pricing import resolve_discount_fields
from apps.finance.services.workorder_financial_movements import sync_workorder_financial_movement


def sync_budget_discount_to_workorder(*, budget) -> object | None:
    workorder = budget.workorders.order_by("pk").first()
    if workorder is None:
        return None

    workorder.apply_discount(budget.resolved_discount_value, budget.resolved_discount_percentage)
    sync_workorder_financial_movement(workorder=workorder)
    return workorder


def sync_workorder_discount_to_budget(*, workorder, discount_value: Money | None = None, discount_percentage: Decimal | None = None, discount_type: str | None = None) -> tuple[Money, Decimal]:
    workorder.invalidate_pricing_snapshot_cache()
    resolved_discount_value, resolved_discount_percentage = resolve_discount_fields(
        total_base_value=workorder.total_base_value,
        discount_value=discount_value,
        discount_percentage=discount_percentage,
    )

    workorder.apply_discount(resolved_discount_value, resolved_discount_percentage, discount_type=discount_type)
    sync_workorder_financial_movement(workorder=workorder)

    budget = workorder.budget
    budget.discount_value = resolved_discount_value
    budget.discount_percentage = Decimal("0.00")
    budget.save(update_fields=["discount_value", "discount_percentage"])

    sync_budget_discount_to_workorder(budget=budget)
    return budget.resolved_discount_value, budget.resolved_discount_percentage
