from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_DOWN


@dataclass(frozen=True)
class Installment:
    number: int
    total: int
    amount: Decimal
    due_date: date


class InstallmentScheduleError(ValueError):
    pass


def build_installments(*, total_amount: Decimal, first_due_date: date, installments_count: int) -> list[Installment]:
    total = max(int(installments_count or 1), 1)
    total_cents = int((Decimal(total_amount) * 100).quantize(Decimal("1"), rounding=ROUND_DOWN))
    amount_per_installment, remaining_cents = divmod(total_cents, total)
    return [
        Installment(
            number=index + 1,
            total=total,
            amount=Decimal(amount_per_installment + (remaining_cents if index == total - 1 else 0)) / Decimal("100"),
            due_date=_add_months(first_due_date, index),
        )
        for index in range(total)
    ]


def parse_installment_schedule(*, due_dates: list[str], amounts: list[str], expected_count: int, expected_total: Decimal) -> list[Installment]:
    expected = max(int(expected_count or 0), 0)
    if expected < 1:
        raise InstallmentScheduleError("Informe a quantidade de parcelas.")
    if len(due_dates) != expected or len(amounts) != expected:
        raise InstallmentScheduleError("Informe data e valor de todas as parcelas.")

    installments: list[Installment] = []
    parsed_total = Decimal("0.00")
    for index, (raw_due_date, raw_amount) in enumerate(zip(due_dates, amounts, strict=True)):
        try:
            due_date = date.fromisoformat(str(raw_due_date).strip())
        except ValueError as exc:
            raise InstallmentScheduleError("Informe uma data de vencimento válida para todas as parcelas.") from exc
        amount = _parse_amount(raw_amount)
        parsed_total += amount
        installments.append(Installment(number=index + 1, total=expected, amount=amount, due_date=due_date))

    if parsed_total != Decimal(expected_total).quantize(Decimal("0.01")):
        raise InstallmentScheduleError("A soma das parcelas deve ser igual ao valor líquido.")
    return installments


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def _parse_amount(raw_value: object) -> Decimal:
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
