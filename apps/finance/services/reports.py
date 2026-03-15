from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from djmoney.money import Money

from apps.finance.models.financial_movement import FinancialMovement


_ZERO_DECIMAL = Decimal("0.00")
_CURRENCY = "BRL"


@dataclass(frozen=True)
class FinancialOverview:
    total_credits: Money
    paid_credits: Money
    total_debits: Money
    paid_debits: Money
    total_result: Money
    confirmed_result: Money


def build_financial_overview(*, workshop, start_date: date, end_date: date) -> FinancialOverview:
    total_credits = _ZERO_DECIMAL
    paid_credits = _ZERO_DECIMAL
    total_debits = _ZERO_DECIMAL
    paid_debits = _ZERO_DECIMAL

    movements = FinancialMovement.objects.filter(
        workshop=workshop,
        due_date__gte=start_date,
        due_date__lte=end_date,
    ).only("direction", "amount", "amount_currency", "is_paid", "workorder", "movement_kind")

    paid_credit_movements = (
        FinancialMovement.objects.filter(
            workshop=workshop,
            direction=FinancialMovement.MovementDirection.CREDIT,
            workorder__isnull=False,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
        )
        .select_related("workorder")
        .prefetch_related("workorder__payments")
        .only("workorder")
    )

    for movement in movements:
        amount = Decimal(getattr(getattr(movement, "amount", None), "amount", _ZERO_DECIMAL) or _ZERO_DECIMAL)
        if movement.direction == FinancialMovement.MovementDirection.CREDIT:
            total_credits += amount
            if movement.is_paid and movement.movement_kind != FinancialMovement.MovementKind.WORKORDER_PARENT:
                paid_credits += amount
            continue
        if movement.direction == FinancialMovement.MovementDirection.DEBIT:
            total_debits += amount
            if movement.is_paid and movement.movement_kind != FinancialMovement.MovementKind.WORKORDER_PARENT:
                paid_debits += amount

    counted_workorders: set[int] = set()
    for movement in paid_credit_movements:
        workorder_id = movement.workorder_id
        if workorder_id is None or workorder_id in counted_workorders:
            continue

        counted_workorders.add(workorder_id)
        for payment in movement.workorder.payments.all():
            if payment.due_date is None or payment.due_date < start_date or payment.due_date > end_date:
                continue
            payment_amount = Decimal(getattr(getattr(payment, "total_paid", None), "amount", _ZERO_DECIMAL) or _ZERO_DECIMAL)
            paid_credits += payment_amount

    total_result = total_credits - total_debits
    confirmed_result = paid_credits - paid_debits

    return FinancialOverview(
        total_credits=Money(total_credits, _CURRENCY),
        paid_credits=Money(paid_credits, _CURRENCY),
        total_debits=Money(total_debits, _CURRENCY),
        paid_debits=Money(paid_debits, _CURRENCY),
        total_result=Money(total_result, _CURRENCY),
        confirmed_result=Money(confirmed_result, _CURRENCY),
    )


def build_monthly_financial_overview(*, workshop, reference_date: date) -> FinancialOverview:
    month_start = reference_date.replace(day=1)
    next_month = (reference_date.replace(day=28) + date.resolution * 4).replace(day=1)
    month_end = next_month - date.resolution
    return build_financial_overview(workshop=workshop, start_date=month_start, end_date=month_end)


def build_yearly_financial_overview(*, workshop, reference_date: date) -> FinancialOverview:
    year_start = reference_date.replace(month=1, day=1)
    year_end = reference_date.replace(month=12, day=31)
    return build_financial_overview(workshop=workshop, start_date=year_start, end_date=year_end)
