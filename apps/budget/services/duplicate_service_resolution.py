"""Detect and resolve duplicate catalog services across avulso items and kits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from enum import Enum
from typing import Literal

from django.db import transaction
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem, BudgetKitItemOverride
from apps.budget.pricing import _is_better_service_source, format_duration_display, zero_money
from apps.core.infrastructure.kit_prefetch import budget_kit_overrides_prefetch


class KitLoserAction(str, Enum):
    DEBIT = "debit"
    KEEP_PRICE = "keep_price"


SourceKind = Literal["direct", "kit"]


@dataclass(slots=True)
class DuplicateServiceSource:
    kind: SourceKind
    service_id: int
    budget_item_id: int
    kit_name: str | None
    quantity: int
    duration: timedelta
    selling_total: Money
    unit_selling: Money
    source_key: str
    duration_display: str
    selling_total_display: str
    is_longest: bool = False
    is_highest_value: bool = False


@dataclass(slots=True)
class DuplicateServiceConflict:
    service_id: int
    service_name: str
    sources: list[DuplicateServiceSource]
    recommended_source_key: str


def _annotate_source_comparison_badges(sources: list[DuplicateServiceSource]) -> None:
    if not sources:
        return
    best_duration = max((_timedelta_seconds(source.duration) for source in sources), default=0)
    best_total = max((source.selling_total.amount for source in sources), default=Decimal("0"))
    for source in sources:
        source.is_longest = _timedelta_seconds(source.duration) == best_duration and best_duration > 0
        source.is_highest_value = source.selling_total.amount == best_total and best_total > 0


def _timedelta_seconds(value: timedelta | None) -> int:
    if not value:
        return 0
    return int(value.total_seconds())


def _money_display(value: Money) -> str:
    amount = (value.amount or Decimal("0")).quantize(Decimal("0.01"))
    return f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _source_key(*, kind: SourceKind, budget_item_id: int) -> str:
    return f"{kind}-{budget_item_id}"


def _budget_items_for_conflict_scan(budget: Budget) -> list[BudgetItem]:
    return list(
        budget.items.select_related("service", "kit")
        .prefetch_related(budget_kit_overrides_prefetch())
        .order_by("id")
    )


def find_duplicate_service_conflicts(budget: Budget) -> list[DuplicateServiceConflict]:
    """Return catalog services that appear in 2+ active sources (avulso and/or kit)."""
    by_service: dict[int, list[DuplicateServiceSource]] = {}
    names: dict[int, str] = {}

    for item in _budget_items_for_conflict_scan(budget):
        if item.is_local:
            continue

        if item.service_id and not item.kit_id and not item.product_id:
            service_id = int(item.service_id)
            quantity = int(item.quantity or 0)
            if quantity <= 0:
                continue
            duration = item.duration or timedelta()
            unit = item.service_selling_price or zero_money()
            total = unit * quantity
            names[service_id] = item.description or getattr(item.service, "name", "") or f"Serviço #{service_id}"
            by_service.setdefault(service_id, []).append(
                DuplicateServiceSource(
                    kind="direct",
                    service_id=service_id,
                    budget_item_id=int(item.pk),
                    kit_name=None,
                    quantity=quantity,
                    duration=duration * quantity if duration else timedelta(),
                    selling_total=total,
                    unit_selling=unit,
                    source_key=_source_key(kind="direct", budget_item_id=int(item.pk)),
                    duration_display=format_duration_display(duration * quantity if duration else timedelta()),
                    selling_total_display=_money_display(total),
                )
            )
            continue

        if not item.kit_id:
            continue

        kit_quantity = int(item.quantity or 0)
        if kit_quantity <= 0:
            continue

        for override in item._iter_frozen_kit_service_overrides():
            if int(getattr(override, "quantity", 0) or 0) <= 0:
                continue
            if getattr(override, "excluded_from_composition", False):
                continue
            service_id = int(override.service_id)
            per_kit_qty = int(override.quantity)
            total_qty = per_kit_qty * kit_quantity
            unit = override.service_selling_price or zero_money()
            total = unit * total_qty
            duration_unit = override.duration or timedelta()
            duration_total = duration_unit * total_qty if duration_unit else timedelta()
            service = override.service
            names[service_id] = getattr(service, "name", "") or f"Serviço #{service_id}"
            kit_name = item.description or getattr(item.kit, "name", "") or f"Kit #{item.kit_id}"
            by_service.setdefault(service_id, []).append(
                DuplicateServiceSource(
                    kind="kit",
                    service_id=service_id,
                    budget_item_id=int(item.pk),
                    kit_name=kit_name,
                    quantity=total_qty,
                    duration=duration_total,
                    selling_total=total,
                    unit_selling=unit,
                    source_key=_source_key(kind="kit", budget_item_id=int(item.pk)),
                    duration_display=format_duration_display(duration_total),
                    selling_total_display=_money_display(total),
                )
            )

    conflicts: list[DuplicateServiceConflict] = []
    for service_id, sources in sorted(by_service.items(), key=lambda pair: pair[0]):
        if len(sources) < 2:
            continue
        recommended = sources[0]
        for candidate in sources[1:]:
            if _is_better_service_source(
                candidate_duration=candidate.duration,
                candidate_total=candidate.selling_total,
                current_duration=recommended.duration,
                current_total=recommended.selling_total,
            ):
                recommended = candidate
        _annotate_source_comparison_badges(sources)
        conflicts.append(
            DuplicateServiceConflict(
                service_id=service_id,
                service_name=names.get(service_id, f"Serviço #{service_id}"),
                sources=sources,
                recommended_source_key=recommended.source_key,
            )
        )
    return conflicts


def filter_conflicts_touching_items(
    conflicts: list[DuplicateServiceConflict],
    *,
    item_ids: list[int] | set[int],
) -> list[DuplicateServiceConflict]:
    touched = {int(item_id) for item_id in item_ids}
    if not touched:
        return []
    return [conflict for conflict in conflicts if any(source.budget_item_id in touched for source in conflict.sources)]


def get_conflict_for_service(budget: Budget, *, service_id: int) -> DuplicateServiceConflict | None:
    for conflict in find_duplicate_service_conflicts(budget):
        if conflict.service_id == int(service_id):
            return conflict
    return None


@transaction.atomic
def apply_duplicate_service_resolution(
    *,
    budget: Budget,
    service_id: int,
    keep_source_key: str,
    kit_loser_actions: dict[str, str],
) -> None:
    """Keep one source for the service; remove or exclude the others."""
    conflict = get_conflict_for_service(budget, service_id=service_id)
    if conflict is None:
        return

    keep_key = str(keep_source_key).strip()
    keep_source = next((source for source in conflict.sources if source.source_key == keep_key), None)
    if keep_source is None:
        raise ValueError("Fonte a manter inválida para o serviço duplicado.")

    for source in conflict.sources:
        if source.source_key == keep_key:
            continue

        if source.kind == "direct":
            BudgetItem.objects.filter(pk=source.budget_item_id, budget_id=budget.pk).delete()
            continue

        action_raw = kit_loser_actions.get(source.source_key) or kit_loser_actions.get(str(source.budget_item_id))
        try:
            action = KitLoserAction(str(action_raw))
        except ValueError as exc:
            raise ValueError(
                f"Escolha se o serviço removido do kit deve debitar ou manter o valor ({source.kit_name or 'kit'})."
            ) from exc

        override = (
            BudgetKitItemOverride.objects.select_related("budget_item")
            .filter(budget_item_id=source.budget_item_id, service_id=service_id)
            .first()
        )
        if override is None:
            continue

        if action == KitLoserAction.DEBIT:
            override.quantity = 0
            override.excluded_from_composition = False
        else:
            override.excluded_from_composition = True
        override.save(update_fields=["quantity", "excluded_from_composition"])
        kit_item = override.budget_item
        kit_item._clear_kit_snapshot_caches()
        kit_item.refresh_kit_snapshot_totals()

    budget.invalidate_pricing_snapshot_cache()
    budget.refresh_stored_total_amount()


@transaction.atomic
def rollback_added_budget_items(*, budget: Budget, item_ids: list[int] | set[int]) -> int:
    """Delete budget items created in the current add flow (cancel duplicate modal)."""
    ids = [int(item_id) for item_id in item_ids if item_id]
    if not ids:
        return 0
    deleted, _ = BudgetItem.objects.filter(budget_id=budget.pk, pk__in=ids).delete()
    budget.invalidate_pricing_snapshot_cache()
    budget.refresh_stored_total_amount()
    return int(deleted)
