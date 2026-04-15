from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.payment_method_fees import calculate_payment_method_fee_amount
from apps.finance.services.workorder_financial_movements import sync_workorder_card_fee_movements
from apps.sources.models import Source
from apps.stock.financial_entries import normalize_entry_type
from apps.stock.models import StockImport
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod


_ZERO = Decimal("0.00")
_FEE_DESCRIPTION = "Pagamento da taxa da maquininha"


@dataclass
class RepairStats:
    scanned: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0
    unresolved_payment_methods: int = 0

    @property
    def changed(self) -> int:
        return self.created + self.updated + self.deleted


def _resolve_decimal_amount(value: object) -> Decimal:
    return Decimal(str(getattr(value, "amount", value) or _ZERO))


def _resolve_payment_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return timezone.localtime(value).date() if timezone.is_aware(value) else value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _workorder_fee_amount(payment: WorkOrderPaymentMethod) -> Decimal:
    return calculate_payment_method_fee_amount(
        payment_method=payment.payment_method,
        base_amount=_resolve_decimal_amount(payment.total_paid),
    )


def _movement_amount(movement: FinancialMovement) -> Decimal:
    return _resolve_decimal_amount(movement.amount)


def _stock_payment_method(*, stock_import: StockImport, payment_entry: dict[str, Any]) -> PaymentMethod | None:
    method_id = payment_entry.get("method")
    if method_id in (None, ""):
        return None

    try:
        return PaymentMethod.objects.filter(pk=int(str(method_id).strip()), workshop=stock_import.workshop).first()
    except (TypeError, ValueError):
        method_description = str(method_id).strip()
        if not method_description:
            return None
        return PaymentMethod.objects.filter(workshop=stock_import.workshop, description__iexact=method_description).order_by("pk").first()


def _get_stock_source(*, stock_import: StockImport, create: bool) -> Source | None:
    source_name = stock_import.supplier_name or "Fornecedor da Importacao"
    source_cnpj = stock_import.supplier_cnpj or ""
    queryset = Source.objects.filter(workshop=stock_import.workshop, name=source_name)
    if not create:
        return queryset.first()
    source, _ = Source.objects.get_or_create(workshop=stock_import.workshop, name=source_name, defaults={"cnpj": source_cnpj})
    return source


def _workorder_movement_needs_update(
    *,
    movement: FinancialMovement,
    payment: WorkOrderPaymentMethod,
    workorder: WorkOrder,
    expected_amount: Decimal,
) -> bool:
    return any(
        [
            movement.workshop_id != workorder.workshop_id,
            movement.user_id != getattr(workorder.budget, "cost_estimator_id", None),
            movement.workorder_id != workorder.pk,
            movement.workorder_payment_id != payment.pk,
            movement.direction != FinancialMovement.MovementDirection.DEBIT,
            movement.description != _FEE_DESCRIPTION,
            movement.payment_method_id != getattr(payment, "payment_method_id", None),
            _movement_amount(movement) != expected_amount,
            movement.due_date != payment.due_date,
            movement.is_paid is not True,
            movement.dre_topic != FinancialMovement.DreTopic.DESPESAS_FINANCEIRAS,
            getattr(getattr(movement, "source", None), "name", None) != f"OS Nº {workorder.pk}",
        ]
    )


def _stock_movement_needs_update(
    *,
    movement: FinancialMovement,
    stock_import: StockImport,
    payment_method: PaymentMethod | None,
    expected_amount: Decimal,
    expected_due_date: date | None,
    expected_source_name: str,
) -> bool:
    return any(
        [
            movement.workshop_id != stock_import.workshop_id,
            movement.user_id != stock_import.user_id,
            movement.direction != FinancialMovement.MovementDirection.DEBIT,
            movement.description != _FEE_DESCRIPTION,
            movement.payment_method_id != getattr(payment_method, "pk", None),
            movement.nf_number != stock_import.nf_number,
            _movement_amount(movement) != expected_amount,
            movement.due_date != expected_due_date,
            movement.is_paid is not False,
            getattr(getattr(movement, "source", None), "name", None) != expected_source_name,
        ]
    )


class Command(BaseCommand):
    help = "Recalcula movimentos de taxa da maquininha para O.S. e importacoes de estoque."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--workshop-id", type=int)

    def handle(self, *args, **options) -> None:
        dry_run = bool(options.get("dry_run"))
        workshop_id = options.get("workshop_id")

        if dry_run:
            workorder_stats = self._repair_workorder_fee_movements(dry_run=True, workshop_id=workshop_id)
            stock_stats = self._repair_stock_fee_movements(dry_run=True, workshop_id=workshop_id)
        else:
            with transaction.atomic():
                workorder_stats = self._repair_workorder_fee_movements(dry_run=False, workshop_id=workshop_id)
                stock_stats = self._repair_stock_fee_movements(dry_run=False, workshop_id=workshop_id)

        message = (
            f"O.S. -> analisadas: {workorder_stats.scanned}, criadas: {workorder_stats.created}, "
            f"atualizadas: {workorder_stats.updated}, removidas: {workorder_stats.deleted}, inalteradas: {workorder_stats.unchanged}, "
            f"formas nao resolvidas: {workorder_stats.unresolved_payment_methods}. "
            f"Estoque -> analisadas: {stock_stats.scanned}, criadas: {stock_stats.created}, atualizadas: {stock_stats.updated}, "
            f"removidas: {stock_stats.deleted}, inalteradas: {stock_stats.unchanged}, formas nao resolvidas: {stock_stats.unresolved_payment_methods}."
        )
        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry-run concluido. {message}"))
            return

        self.stdout.write(self.style.SUCCESS(f"Reparo concluido. {message}"))

    def _repair_workorder_fee_movements(self, *, dry_run: bool, workshop_id: int | None) -> RepairStats:
        stats = RepairStats()
        queryset = WorkOrder.objects.filter(Q(payments__isnull=False) | Q(financial_movements__movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE)).distinct()
        if workshop_id is not None:
            queryset = queryset.filter(workshop_id=workshop_id)

        queryset = queryset.select_related("budget", "budget__cost_estimator")

        for workorder in queryset.iterator():
            stats.scanned += 1
            payment_list = list(workorder.payments.select_related("payment_method"))
            existing_movements = list(
                FinancialMovement.objects.filter(
                    workorder=workorder,
                    movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
                )
                .select_related("source", "payment_method")
                .order_by("pk")
            )

            existing_by_payment_id: dict[int, list[FinancialMovement]] = {}
            orphaned_movements: list[FinancialMovement] = []
            for movement in existing_movements:
                if movement.workorder_payment_id is None:
                    orphaned_movements.append(movement)
                    continue
                existing_by_payment_id.setdefault(movement.workorder_payment_id, []).append(movement)

            should_sync = False
            stats.deleted += len(orphaned_movements)
            if orphaned_movements:
                should_sync = True

            for payment in payment_list:
                expected_amount = _workorder_fee_amount(payment)
                movements = existing_by_payment_id.pop(payment.pk, [])
                duplicates = movements[1:]
                movement = movements[0] if movements else None

                if duplicates:
                    stats.deleted += len(duplicates)
                    should_sync = True

                if expected_amount <= _ZERO:
                    if movement is not None:
                        stats.deleted += 1
                        should_sync = True
                    continue

                if movement is None:
                    stats.created += 1
                    should_sync = True
                    continue

                if _workorder_movement_needs_update(
                    movement=movement,
                    payment=payment,
                    workorder=workorder,
                    expected_amount=expected_amount,
                ):
                    stats.updated += 1
                    should_sync = True
                else:
                    stats.unchanged += 1

            stale_count = sum(len(movements) for movements in existing_by_payment_id.values())
            if stale_count:
                stats.deleted += stale_count
                should_sync = True

            if should_sync and not dry_run:
                sync_workorder_card_fee_movements(workorder=workorder)

        return stats

    def _repair_stock_fee_movements(self, *, dry_run: bool, workshop_id: int | None) -> RepairStats:
        stats = RepairStats()
        queryset = StockImport.objects.all()
        if workshop_id is not None:
            queryset = queryset.filter(workshop_id=workshop_id)

        for stock_import in queryset.iterator():
            entries = list(stock_import.payments_data or [])
            if not entries:
                continue

            stats.scanned += 1
            payments_changed = False

            for payment_entry in entries:
                fee_movement_id = payment_entry.get("fee_financial_movement_id")
                fee_movement = None
                if fee_movement_id:
                    fee_movement = FinancialMovement.objects.filter(pk=fee_movement_id, workshop=stock_import.workshop).select_related("source", "payment_method").first()

                if normalize_entry_type(payment_entry) != "payment":
                    if fee_movement is not None:
                        stats.deleted += 1
                        if not dry_run:
                            fee_movement.delete()
                    if fee_movement_id:
                        payments_changed = True
                        if not dry_run:
                            payment_entry["fee_financial_movement_id"] = None
                    continue

                payment_method = _stock_payment_method(stock_import=stock_import, payment_entry=payment_entry)
                if payment_method is None and payment_entry.get("method") not in (None, ""):
                    stats.unresolved_payment_methods += 1
                total_paid = _resolve_decimal_amount(payment_entry.get("total_paid", _ZERO))
                expected_amount = calculate_payment_method_fee_amount(payment_method=payment_method, base_amount=total_paid)
                expected_due_date = _resolve_payment_date(payment_entry.get("payment_date"))
                expected_source_name = stock_import.supplier_name or "Fornecedor da Importacao"
                payment_movement = None
                payment_movement_id = payment_entry.get("financial_movement_id")
                if payment_movement_id:
                    payment_movement = FinancialMovement.objects.filter(pk=payment_movement_id, workshop=stock_import.workshop).select_related("source").first()

                if expected_amount <= _ZERO:
                    if fee_movement is not None:
                        stats.deleted += 1
                        if not dry_run:
                            fee_movement.delete()
                    if fee_movement_id:
                        payments_changed = True
                        if not dry_run:
                            payment_entry["fee_financial_movement_id"] = None
                    continue

                if fee_movement is None:
                    stats.created += 1
                    if dry_run:
                        continue

                    source = payment_movement.source if payment_movement is not None else _get_stock_source(stock_import=stock_import, create=True)
                    new_fee_movement = FinancialMovement.objects.create(
                        workshop=stock_import.workshop,
                        user=stock_import.user,
                        source=source,
                        direction=FinancialMovement.MovementDirection.DEBIT,
                        description=_FEE_DESCRIPTION,
                        payment_method=payment_method,
                        nf_number=stock_import.nf_number,
                        amount=expected_amount,
                        due_date=expected_due_date,
                        is_paid=False,
                    )
                    payment_entry["fee_financial_movement_id"] = new_fee_movement.pk
                    payments_changed = True
                    continue

                if _stock_movement_needs_update(
                    movement=fee_movement,
                    stock_import=stock_import,
                    payment_method=payment_method,
                    expected_amount=expected_amount,
                    expected_due_date=expected_due_date,
                    expected_source_name=expected_source_name,
                ):
                    stats.updated += 1
                    if not dry_run:
                        source = payment_movement.source if payment_movement is not None else _get_stock_source(stock_import=stock_import, create=True)
                        fee_movement.workshop = stock_import.workshop
                        fee_movement.user = stock_import.user
                        fee_movement.source = source
                        fee_movement.direction = FinancialMovement.MovementDirection.DEBIT
                        fee_movement.description = _FEE_DESCRIPTION
                        fee_movement.payment_method = payment_method
                        fee_movement.nf_number = stock_import.nf_number
                        fee_movement.amount = expected_amount
                        fee_movement.due_date = expected_due_date
                        fee_movement.is_paid = False
                        fee_movement.save(
                            update_fields=[
                                "workshop",
                                "user",
                                "source",
                                "direction",
                                "description",
                                "payment_method",
                                "nf_number",
                                "amount",
                                "due_date",
                                "is_paid",
                            ]
                        )
                else:
                    stats.unchanged += 1

                if fee_movement_id != fee_movement.pk:
                    payments_changed = True
                    if not dry_run:
                        payment_entry["fee_financial_movement_id"] = fee_movement.pk

            if payments_changed and not dry_run:
                stock_import.payments_data = entries
                stock_import.save(update_fields=["payments_data"])

        return stats
