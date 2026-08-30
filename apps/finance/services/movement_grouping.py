from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_DOWN, InvalidOperation


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


class InstallmentScheduleError(ValueError):
    pass


def _parse_money_amount(raw_value: object) -> Decimal:
    text = str(raw_value or "").strip().replace("R$", "").strip()
    if not text:
        raise InstallmentScheduleError("Informe o valor de todas as parcelas.")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise InstallmentScheduleError("Informe valores numéricos válidos para as parcelas.") from exc
    if amount <= 0:
        raise InstallmentScheduleError("O valor de cada parcela deve ser maior que zero.")
    return amount.quantize(Decimal("0.01"))


def parse_group_installment_schedule(
    *,
    due_dates: list[str],
    amounts: list[str],
    expected_count: int,
    expected_total: Decimal,
) -> list[GroupInstallment]:
    expected = max(int(expected_count or 0), 0)
    if expected < 1:
        raise InstallmentScheduleError("Informe a quantidade de parcelas.")
    if len(due_dates) != expected or len(amounts) != expected:
        raise InstallmentScheduleError("Informe data e valor de todas as parcelas.")

    parsed_total = Decimal("0.00")
    installments: list[GroupInstallment] = []
    for index, (raw_due_date, raw_amount) in enumerate(zip(due_dates, amounts, strict=True)):
        try:
            due_date = date.fromisoformat(str(raw_due_date).strip())
        except ValueError as exc:
            raise InstallmentScheduleError("Informe uma data de vencimento válida para todas as parcelas.") from exc
        amount = _parse_money_amount(raw_amount)
        parsed_total += amount
        installments.append(GroupInstallment(number=index + 1, total=expected, amount=amount, due_date=due_date))

    expected_total = Decimal(expected_total).quantize(Decimal("0.01"))
    if parsed_total != expected_total:
        raise InstallmentScheduleError("A soma das parcelas deve ser igual ao total agrupado.")
    return installments
