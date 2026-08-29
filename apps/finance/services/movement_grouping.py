from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_DOWN


@dataclass(frozen=True)
class GroupInstallment:
    number: int
    total: int
    amount: Decimal
    due_date: date


def build_group_installments(*, total_amount: Decimal, first_due_date: date, installments_count: int) -> list[GroupInstallment]:
    total = max(int(installments_count or 1), 1)
    total_cents = int((Decimal(total_amount) * 100).quantize(Decimal("1"), rounding=ROUND_DOWN))
    amount_per_installment, remaining_cents = divmod(total_cents, total)

    installments: list[GroupInstallment] = []
    for index in range(total):
        amount_cents = amount_per_installment
        if index == total - 1:
            amount_cents += remaining_cents
        installments.append(
            GroupInstallment(
                number=index + 1,
                total=total,
                amount=Decimal(amount_cents) / Decimal("100"),
                due_date=_add_months(first_due_date, index),
            )
        )
    return installments


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + (month_index // 12)
    month = (month_index % 12) + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)
