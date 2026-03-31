from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


PAYMENT_ENTRY_TYPE = "payment"
ADDITIONAL_CHARGE_ENTRY_TYPE = "additional_charge"


def _to_decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def normalize_entry_type(entry: dict[str, Any]) -> str:
    entry_type = str(entry.get("entry_type") or PAYMENT_ENTRY_TYPE).strip()
    return entry_type or PAYMENT_ENTRY_TYPE


def get_entry_amount(entry: dict[str, Any]) -> Decimal:
    if normalize_entry_type(entry) == ADDITIONAL_CHARGE_ENTRY_TYPE:
        return _to_decimal(entry.get("amount", 0))
    return _to_decimal(entry.get("total_paid", 0))


def get_entry_reason(entry: dict[str, Any]) -> str:
    if normalize_entry_type(entry) == ADDITIONAL_CHARGE_ENTRY_TYPE:
        return str(entry.get("reason") or "").strip()
    return str(entry.get("reason") or entry.get("method_display") or "").strip()


def get_next_entry_id(entries: list[dict[str, Any]]) -> int:
    numeric_ids = [int(entry.get("id", 0) or 0) for entry in entries]
    return (max(numeric_ids) if numeric_ids else 0) + 1


@dataclass(frozen=True)
class FinancialTotals:
    total_nf: Decimal
    total_additional: Decimal
    total_paid: Decimal

    @property
    def total_value(self) -> Decimal:
        return self.total_nf + self.total_additional

    @property
    def pending_value(self) -> Decimal:
        return self.total_value - self.total_paid


def calculate_import_totals(*, items: list[dict[str, Any]], entries: list[dict[str, Any]]) -> FinancialTotals:
    total_nf = sum((_to_decimal(item.get("valor", 0)) * _to_decimal(item.get("qtd", 0)) for item in items), start=Decimal("0.00"))
    total_additional = sum((get_entry_amount(entry) for entry in entries if normalize_entry_type(entry) == ADDITIONAL_CHARGE_ENTRY_TYPE), start=Decimal("0.00"))
    total_paid = sum((get_entry_amount(entry) for entry in entries if normalize_entry_type(entry) == PAYMENT_ENTRY_TYPE), start=Decimal("0.00"))
    return FinancialTotals(total_nf=total_nf, total_additional=total_additional, total_paid=total_paid)
