"""Rewrites OS references persisted with the internal PK to the public work order number.

Kept as a module so the mapping/rename logic can be unit tested with real models.
"""

from __future__ import annotations

import logging
import re
from typing import Any


logger = logging.getLogger(__name__)

REVENUE_DESCRIPTION_PREFIX = "Receita proveniente de ordem de serviço"
SOURCE_NAME_PREFIX = "OS Nº "
BATCH_SIZE = 500

_SOURCE_NAME_PATTERN = re.compile(r"^OS Nº (\d+)$")


def resolve_public_number(budget: Any) -> int | None:
    if budget is None:
        return None
    number = getattr(budget, "number", None)
    if number is not None:
        return int(number)
    return int(budget.pk)


def parse_source_workorder_pk(name: str) -> int | None:
    match = _SOURCE_NAME_PATTERN.match((name or "").strip())
    return int(match.group(1)) if match else None


def backfill_workorder_movement_descriptions(*, financial_movement_model: Any) -> int:
    """Rewrites only descriptions still matching the auto-generated PK pattern."""
    queryset = (
        financial_movement_model.objects.filter(
            movement_kind="WORKORDER_PARENT",
            workorder_id__isnull=False,
            description__startswith=REVENUE_DESCRIPTION_PREFIX,
        )
        .select_related("workorder__budget")
        .order_by("pk")
        .iterator(chunk_size=BATCH_SIZE)
    )

    updated = 0
    pending: list[Any] = []
    for movement in queryset:
        workorder = getattr(movement, "workorder", None)
        if workorder is None:
            continue

        public_number = resolve_public_number(getattr(workorder, "budget", None))
        if public_number is None or public_number == workorder.pk:
            continue

        legacy_description = f"{REVENUE_DESCRIPTION_PREFIX} OS Nº {workorder.pk}"
        if (movement.description or "").strip() != legacy_description:
            continue

        movement.description = f"{REVENUE_DESCRIPTION_PREFIX} OS Nº {public_number}"
        pending.append(movement)
        updated += 1
        if len(pending) >= BATCH_SIZE:
            financial_movement_model.objects.bulk_update(pending, ["description"])
            pending.clear()

    if pending:
        financial_movement_model.objects.bulk_update(pending, ["description"])

    return updated


def build_source_rename_plan(*, source_model: Any, financial_movement_model: Any) -> dict[int, str]:
    """Maps Source pk to its new name, skipping sources shared by more than one work order."""
    workorder_ids_by_source: dict[int, set[int]] = {}
    for source_id, workorder_id in financial_movement_model.objects.filter(source_id__isnull=False, workorder_id__isnull=False).values_list("source_id", "workorder_id").distinct():
        workorder_ids_by_source.setdefault(int(source_id), set()).add(int(workorder_id))

    sources = list(source_model.objects.filter(name__startswith=SOURCE_NAME_PREFIX).order_by("pk"))
    if not sources:
        return {}

    candidate_workorder_ids: set[int] = set()
    resolved_workorder_id_by_source: dict[int, int] = {}
    for source in sources:
        linked = workorder_ids_by_source.get(source.pk, set())
        if len(linked) > 1:
            logger.warning("Source %s vinculado a múltiplas OS; renomeação ignorada", source.pk)
            continue
        workorder_id = next(iter(linked), None) or parse_source_workorder_pk(source.name)
        if workorder_id is None:
            continue
        resolved_workorder_id_by_source[source.pk] = workorder_id
        candidate_workorder_ids.add(workorder_id)

    if not candidate_workorder_ids:
        return {}

    workorder_model = financial_movement_model._meta.get_field("workorder").related_model
    public_number_by_workorder_id = {workorder.pk: resolve_public_number(getattr(workorder, "budget", None)) for workorder in workorder_model.objects.filter(pk__in=candidate_workorder_ids).select_related("budget")}

    plan: dict[int, str] = {}
    sources_by_pk = {source.pk: source for source in sources}
    claimed_names: set[tuple[int, str]] = set()
    for source_pk, workorder_id in resolved_workorder_id_by_source.items():
        public_number = public_number_by_workorder_id.get(workorder_id)
        if public_number is None:
            continue
        source = sources_by_pk[source_pk]
        new_name = f"{SOURCE_NAME_PREFIX}{public_number}"
        if source.name == new_name:
            claimed_names.add((source.workshop_id, new_name))
            continue
        if (source.workshop_id, new_name) in claimed_names:
            logger.warning("Source %s não renomeado para %r: nome já reivindicado por outra origem da oficina %s", source_pk, new_name, source.workshop_id)
            continue
        claimed_names.add((source.workshop_id, new_name))
        plan[source_pk] = new_name

    return plan


def rename_workorder_sources(*, source_model: Any, financial_movement_model: Any) -> dict[str, int]:
    """Renames in two phases so swapped names never violate unique_source_name_per_workshop."""
    plan = build_source_rename_plan(source_model=source_model, financial_movement_model=financial_movement_model)
    if not plan:
        return {"renamed": 0, "conflicts": 0}

    sources = list(source_model.objects.filter(pk__in=plan.keys()))
    original_name_by_pk = {source.pk: source.name for source in sources}

    for source in sources:
        source.name = f"__os_migracao_{source.pk}"
    source_model.objects.bulk_update(sources, ["name"], batch_size=BATCH_SIZE)

    renamed = 0
    conflicts = 0
    for source in sources:
        target_name = plan[source.pk]
        is_taken = source_model.objects.filter(workshop_id=source.workshop_id, name=target_name).exclude(pk__in=plan.keys()).exists()
        if is_taken:
            conflicts += 1
            source.name = original_name_by_pk[source.pk]
            logger.warning("Source %s mantido como %r: nome %r já está em uso na oficina %s", source.pk, source.name, target_name, source.workshop_id)
            continue
        source.name = target_name
        renamed += 1

    source_model.objects.bulk_update(sources, ["name"], batch_size=BATCH_SIZE)
    return {"renamed": renamed, "conflicts": conflicts}
