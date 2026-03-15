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
    total_debits = _ZERO_DECIMAL

    movements = FinancialMovement.objects.filter(
        workshop=workshop,
        due_date__gte=start_date,
        due_date__lte=end_date,
    ).only("direction", "amount", "amount_currency")

    for movement in movements:
        amount = Decimal(getattr(getattr(movement, "amount", None), "amount", _ZERO_DECIMAL) or _ZERO_DECIMAL)
        if movement.direction == FinancialMovement.MovementDirection.CREDIT:
            total_credits += amount
            continue
        if movement.direction == FinancialMovement.MovementDirection.DEBIT:
            total_debits += amount

    total_result = total_credits - total_debits

    return FinancialOverview(
        total_credits=Money(total_credits, _CURRENCY),
        paid_credits=Money(_ZERO_DECIMAL, _CURRENCY),
        total_debits=Money(total_debits, _CURRENCY),
        paid_debits=Money(_ZERO_DECIMAL, _CURRENCY),
        total_result=Money(total_result, _CURRENCY),
        confirmed_result=Money(_ZERO_DECIMAL, _CURRENCY),
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
