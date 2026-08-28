from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django import forms
from djmoney.money import Money

from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.sources.models import Source
from apps.suppliers.models import Supplier


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


MISSING_BUDGET_PLAN_MESSAGE = "Selecione o plano orçamentário dos pagamentos antes de finalizar."
MISSING_PAYMENT_METHOD_MESSAGE = "A forma de pagamento de um lançamento da importação é inválida."


def resolve_import_budget_plan(*, workshop: Any, budget_plan_id: Any) -> FinancialGroup | None:
    if budget_plan_id in (None, ""):
        return None
    try:
        pk = int(str(budget_plan_id))
    except (TypeError, ValueError):
        return None
    return FinancialGroup.objects.filter(pk=pk, workshop=workshop).first()


def payment_entry_has_budget_plan(entry: dict[str, Any]) -> bool:
    return entry.get("budget_plan_id") not in (None, "")


def payment_entries_missing_budget_plan(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [entry for entry in entries if normalize_entry_type(entry) == PAYMENT_ENTRY_TYPE and not payment_entry_has_budget_plan(entry)]


def apply_budget_plan_to_payment_entries(*, entries: list[dict[str, Any]], budget_plan_id: int) -> tuple[list[dict[str, Any]], bool]:
    updated = False
    normalized_entries = [dict(entry) for entry in entries]
    for entry in normalized_entries:
        if normalize_entry_type(entry) != PAYMENT_ENTRY_TYPE:
            continue
        if payment_entry_has_budget_plan(entry):
            continue
        entry["budget_plan_id"] = budget_plan_id
        updated = True
    return normalized_entries, updated


def apply_card_fee_budget_plan(*, fee_movement: FinancialMovement, fallback_plan: FinancialGroup | None) -> None:
    if fee_movement.budget_plan_id or fallback_plan is None:
        return
    fee_movement.budget_plan = fallback_plan
    fee_movement.save(update_fields=["budget_plan"])


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
    source_name = stock_import.supplier_name or "Fornecedor da Importação"
    source_cnpj = stock_import.supplier_cnpj or ""
    source, _ = Source.objects.get_or_create(workshop=workshop, name=source_name, defaults={"cnpj": source_cnpj})

    # The stock import stores supplier data as plain NF fields.  Financial grouping,
    # however, relies on the canonical Supplier relation, so resolve it in the same
    # workshop while preserving the existing Source relation for compatibility.
    supplier = None
    if source_cnpj:
        supplier, _ = Supplier.objects.get_or_create(
            workshop=workshop,
            cnpj=source_cnpj,
            defaults={"name": source_name},
        )

    for entry in normalized_entries:
        if normalize_entry_type(entry) != PAYMENT_ENTRY_TYPE:
            continue

        financial_movement_id = entry.get("financial_movement_id")
        if financial_movement_id:
            financial_movement = FinancialMovement.objects.filter(
                pk=financial_movement_id,
                workshop=workshop,
            ).first()
            if financial_movement is not None:
                # Do not replace a supplier selected manually. This also repairs
                # movements created in an earlier import step before finalization.
                if supplier is not None and financial_movement.supplier_id is None:
                    financial_movement.supplier = supplier
                    financial_movement.save(update_fields=["supplier"])
                continue

        payment_method = PaymentMethod.objects.filter(pk=entry.get("method"), workshop=workshop).first()
        if payment_method is None:
            raise forms.ValidationError(MISSING_PAYMENT_METHOD_MESSAGE)

        budget_plan = resolve_import_budget_plan(workshop=workshop, budget_plan_id=entry.get("budget_plan_id"))
        if budget_plan is None:
            raise forms.ValidationError(MISSING_BUDGET_PLAN_MESSAGE)

        financial_movement = FinancialMovement.objects.create(
            workshop=workshop,
            user=user,
            source=source,
            supplier=supplier,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description=f"Pagamento Importação de Estoque - NF: {resolved_nf_number}",
            payment_method=payment_method,
            budget_plan=budget_plan,
            nf_number=stock_import.nf_number,
            amount=Money(get_entry_amount(entry), "BRL"),
            due_date=entry.get("payment_date") or None,
            is_paid=False,
        )
        entry["financial_movement_id"] = financial_movement.pk
        updated = True

    return normalized_entries, updated


def sync_payment_entries_if_budget_plans_ready(*, stock_import: Any, entries: list[dict[str, Any]], user: Any, replace_existing: bool = False) -> tuple[list[dict[str, Any]], bool]:
    if payment_entries_missing_budget_plan(entries):
        return [dict(entry) for entry in entries], False
    return sync_payment_entries_with_financial_movements(
        stock_import=stock_import,
        entries=entries,
        user=user,
        replace_existing=replace_existing,
    )
