from __future__ import annotations

from decimal import Decimal

from djmoney.money import Money

from apps.budget.pricing import resolve_discount_fields
from apps.finance.services.workorder_financial_movements import sync_workorder_financial_movement


def sync_budget_discount_to_workorder(*, budget, entered_as_value: bool | None = None) -> object | None:
    workorder = budget.workorders.order_by("pk").first()
    if workorder is None:
        return None

    if entered_as_value is None:
        budget_pct = budget.discount_percentage or Decimal("0.00")
        budget_value = budget.discount_value or Money(Decimal("0.00"), "BRL")
        entered_as_value = budget_value.amount > 0
        entered_as_percentage = not entered_as_value and budget_pct > 0
    else:
        entered_as_percentage = not entered_as_value

    if entered_as_value:
        workorder.apply_discount(budget.resolved_discount_value, Decimal("0.00"))
    elif entered_as_percentage:
        workorder.apply_discount(Money(Decimal("0.00"), "BRL"), budget.resolved_discount_percentage)
    else:
        workorder.apply_discount(Money(Decimal("0.00"), "BRL"), Decimal("0.00"))
    sync_workorder_financial_movement(workorder=workorder)
    return workorder


def sync_workorder_discount_to_budget(*, workorder, discount_value: Money | None = None, discount_percentage: Decimal | None = None, discount_type: str | None = None) -> tuple[Money, Decimal]:
    workorder.invalidate_pricing_snapshot_cache()

    raw_discount_amount = discount_value.amount if discount_value is not None else Decimal("0.00")
    raw_discount_percentage = discount_percentage or Decimal("0.00")
    entered_as_value = raw_discount_amount > 0
    entered_as_percentage = not entered_as_value and raw_discount_percentage > 0

    resolved_discount_value, resolved_discount_percentage = resolve_discount_fields(
        total_base_value=workorder.total_base_value,
        discount_value=discount_value,
        discount_percentage=discount_percentage,
    )

    if entered_as_value:
        workorder.apply_discount(resolved_discount_value, Decimal("0.00"), discount_type=discount_type)
    elif entered_as_percentage:
        workorder.apply_discount(Money(Decimal("0.00"), "BRL"), resolved_discount_percentage, discount_type=discount_type)
    else:
        workorder.apply_discount(Money(Decimal("0.00"), "BRL"), Decimal("0.00"), discount_type=discount_type)

    sync_workorder_financial_movement(workorder=workorder)

    budget = workorder.budget
    budget.discount_value = resolved_discount_value if entered_as_value else Money(Decimal("0.00"), "BRL")
    budget.discount_percentage = resolved_discount_percentage if entered_as_percentage else Decimal("0.00")
    budget.save(update_fields=["discount_value", "discount_percentage"])

    return budget.resolved_discount_value, budget.resolved_discount_percentage
