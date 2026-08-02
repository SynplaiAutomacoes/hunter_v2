from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from djmoney.money import Money

from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.sources.models import Source


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


def sync_payment_entries_with_financial_movements(*, stock_import: Any, entries: list[dict[str, Any]], user: Any, replace_existing: bool = False) -> tuple[list[dict[str, Any]], bool]:
    workshop = stock_import.workshop
    normalized_entries = [dict(entry) for entry in entries]
    updated = False

    if replace_existing:
        current_financial_movement_ids = {int(entry.get("financial_movement_id")) for entry in normalized_entries if normalize_entry_type(entry) == PAYMENT_ENTRY_TYPE and entry.get("financial_movement_id")}
        stale_financial_movement_ids = {int(entry.get("financial_movement_id")) for entry in list(stock_import.payments_data or []) if normalize_entry_type(entry) == PAYMENT_ENTRY_TYPE and entry.get("financial_movement_id") and int(entry.get("financial_movement_id")) not in current_financial_movement_ids}
        if stale_financial_movement_ids:
            FinancialMovement.objects.filter(workshop=workshop, pk__in=stale_financial_movement_ids).delete()

    resolved_nf_number = getattr(stock_import, "nf_number_display", None) or stock_import.nf_number or "S/N"
    source_name = stock_import.supplier_name or "Fornecedor da importação"
    source_cnpj = stock_import.supplier_cnpj or ""
    source, _ = Source.objects.get_or_create(workshop=workshop, name=source_name, defaults={"cnpj": source_cnpj})

    for entry in normalized_entries:
        if normalize_entry_type(entry) != PAYMENT_ENTRY_TYPE:
            continue

        financial_movement_id = entry.get("financial_movement_id")
        if financial_movement_id and FinancialMovement.objects.filter(pk=financial_movement_id, workshop=workshop).exists():
            continue

        payment_method = PaymentMethod.objects.filter(pk=entry.get("method"), workshop=workshop).first()
        if payment_method is None:
            raise PaymentMethod.DoesNotExist(f"Forma de pagamento {entry.get('method')} não encontrada para a oficina {workshop.pk}.")

        financial_movement = FinancialMovement.objects.create(
            workshop=workshop,
            user=user,
            source=source,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description=f"Pagamento Importação de Estoque - NF: {resolved_nf_number}",
            payment_method=payment_method,
            nf_number=stock_import.nf_number,
            amount=Money(get_entry_amount(entry), "BRL"),
            due_date=entry.get("payment_date") or None,
            is_paid=False,
        )
        entry["financial_movement_id"] = financial_movement.pk
        updated = True

    return normalized_entries, updated
