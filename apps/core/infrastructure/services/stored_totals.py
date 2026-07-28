from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TypeVar

from django.db import transaction
from django.db.models import Model, QuerySet
from djmoney.money import Money

from apps.budget.models import Budget
from apps.core.infrastructure.kit_prefetch import budget_items_with_kit_prefetch, workorder_items_with_kit_prefetch
from apps.workorder.models import WorkOrder


ModelT = TypeVar("ModelT", bound=Model)


@dataclass(frozen=True, slots=True)
class StoredTotalsBackfillResult:
    budgets_scanned: int
    budgets_updated: int
    workorders_scanned: int
    workorders_updated: int


def _iter_batches(queryset: QuerySet[ModelT], *, batch_size: int) -> Iterator[list[ModelT]]:
    batch: list[ModelT] = []
    for instance in queryset.iterator(chunk_size=batch_size):
        batch.append(instance)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def backfill_stored_totals(
    *,
    batch_size: int = 250,
    workshop_id: int | None = None,
    budget_types: frozenset[str] | set[str] | None = None,
) -> StoredTotalsBackfillResult:
    """Rebuild denormalized totals with the canonical pricing and payment rules.

    This is intentionally an idempotent maintenance operation instead of a data
    migration: historical Django models cannot safely reproduce the complete
    pricing graph (kits, benefits, discounts and frozen workshop costs).

    Pass ``budget_types`` (e.g. ``{\"warranty\", \"courtesy\"}``) to limit the
    rebuild to those document types — useful for targeted retroactive fixes.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")

    budget_queryset = Budget.objects.select_related("workshop").prefetch_related(budget_items_with_kit_prefetch()).order_by("pk")
    workorder_queryset = (
        WorkOrder.objects.select_related("workshop", "budget", "budget__workshop")
        .prefetch_related(workorder_items_with_kit_prefetch(), "payments")
        .order_by("pk")
    )
    if workshop_id is not None:
        budget_queryset = budget_queryset.filter(workshop_id=workshop_id)
        workorder_queryset = workorder_queryset.filter(workshop_id=workshop_id)
    if budget_types is not None:
        budget_queryset = budget_queryset.filter(budget_type__in=budget_types)
        workorder_queryset = workorder_queryset.filter(budget_type__in=budget_types)

    budgets_scanned = 0
    budgets_updated = 0
    for budgets in _iter_batches(budget_queryset, batch_size=batch_size):
        changed_budgets: list[Budget] = []
        for budget in budgets:
            stored_total_before = budget.stored_total_amount
            canonical_total = Money(budget.stored_total_source_value.amount, "BRL")
            if stored_total_before != canonical_total:
                budgets_updated += 1
            if budget.stored_total_amount != canonical_total:
                budget.stored_total_amount = canonical_total
                changed_budgets.append(budget)
        if changed_budgets:
            with transaction.atomic():
                Budget.objects.bulk_update(changed_budgets, ["stored_total_amount"], batch_size=batch_size)
        budgets_scanned += len(budgets)

    workorders_scanned = 0
    workorders_updated = 0
    for workorders in _iter_batches(workorder_queryset, batch_size=batch_size):
        changed_workorders: list[WorkOrder] = []
        for workorder in workorders:
            stored_total_before = workorder.stored_total_amount
            stored_paid_before = workorder.stored_paid_amount
            canonical_total = Money(workorder.stored_total_source_value.amount, "BRL")
            canonical_paid = Money(workorder.paid_value.amount, "BRL")
            if stored_total_before != canonical_total or stored_paid_before != canonical_paid:
                workorders_updated += 1
            if workorder.stored_total_amount != canonical_total or workorder.stored_paid_amount != canonical_paid:
                workorder.stored_total_amount = canonical_total
                workorder.stored_paid_amount = canonical_paid
                changed_workorders.append(workorder)
        if changed_workorders:
            with transaction.atomic():
                WorkOrder.objects.bulk_update(changed_workorders, ["stored_total_amount", "stored_paid_amount"], batch_size=batch_size)
        workorders_scanned += len(workorders)

    return StoredTotalsBackfillResult(
        budgets_scanned=budgets_scanned,
        budgets_updated=budgets_updated,
        workorders_scanned=workorders_scanned,
        workorders_updated=workorders_updated,
    )
