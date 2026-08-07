from __future__ import annotations

from django.db import transaction
from django.db.models import Value
from django.db.models.functions import Concat, Substr

from apps.finance.models.financial_group import FinancialGroup


def cascade_delete_with_renumber(*, workshop_id: int, group_ids: list[int]) -> int:
    valid_ids = _filter_valid_group_ids(workshop_id, group_ids)
    if not valid_ids:
        return 0

    target_ids = _collect_all_target_ids(valid_ids)

    if not target_ids:
        return 0

    with transaction.atomic():
        groups_to_delete = list(
            FinancialGroup.objects.select_for_update().filter(pk__in=target_ids)
        )
        parent_ids = {g.parent_id for g in groups_to_delete}

        for parent_id in parent_ids:
            list(
                FinancialGroup.objects.filter(
                    workshop_id=workshop_id,
                    parent_id=parent_id,
                )
                .exclude(pk__in=target_ids)
                .select_for_update()
            )

        groups_to_delete.sort(key=lambda g: g.level, reverse=True)
        delete_count = len(groups_to_delete)
        for group in groups_to_delete:
            group.delete()

        for parent_id in parent_ids:
            _renumber_level(workshop_id=workshop_id, parent_id=parent_id)

        return delete_count


def collect_descendant_ids(group_id: int) -> list[int]:
    ids: list[int] = []
    _walk_descendants(parent_id=group_id, ids=ids)
    return ids


def _filter_valid_group_ids(workshop_id: int, group_ids: list[int]) -> list[int]:
    return list(
        FinancialGroup.objects.filter(
            pk__in=group_ids,
            workshop_id=workshop_id,
        ).values_list("pk", flat=True)
    )


def _collect_all_target_ids(group_ids: list[int]) -> set[int]:
    target_ids: set[int] = set()
    for gid in group_ids:
        target_ids.add(gid)
        target_ids.update(collect_descendant_ids(gid))
    return target_ids


def _walk_descendants(*, parent_id: int, ids: list[int]) -> None:
    children = FinancialGroup.objects.filter(parent_id=parent_id).only("pk")
    for child in children:
        ids.append(child.pk)
        _walk_descendants(parent_id=child.pk, ids=ids)


def _renumber_level(*, workshop_id: int, parent_id: int | None) -> None:
    siblings = list(
        FinancialGroup.objects.filter(
            workshop_id=workshop_id,
            parent_id=parent_id,
        ).order_by("sequence")
    )

    parent = None
    if parent_id is not None:
        parent = (
            FinancialGroup.objects.filter(pk=parent_id)
            .only("code", "sort_key")
            .first()
        )

    parent_code: str | None = parent.code if parent else None
    parent_sort_key: str | None = parent.sort_key if parent else None

    for idx, group in enumerate(siblings, start=1):
        new_sequence = idx
        if group.sequence == new_sequence:
            continue

        new_code = _build_code(parent_code=parent_code, sequence=new_sequence)
        new_sort_key = _build_sort_key(
            parent_sort_key=parent_sort_key, sequence=new_sequence
        )

        old_code = group.code
        old_sort_key = group.sort_key

        FinancialGroup.objects.filter(pk=group.pk).update(
            sequence=new_sequence,
            code=new_code,
            sort_key=new_sort_key,
        )

        if old_sort_key:
            old_prefix = f"{old_sort_key}."
            FinancialGroup.objects.filter(
                workshop_id=workshop_id,
                sort_key__startswith=old_prefix,
            ).update(
                sort_key=Concat(
                    Value(f"{new_sort_key}."),
                    Substr("sort_key", len(old_sort_key) + 2),
                ),
                code=Concat(
                    Value(f"{new_code}."),
                    Substr("code", len(old_code) + 2),
                ),
            )


def _build_code(*, parent_code: str | None, sequence: int) -> str:
    if parent_code is None:
        return str(sequence)
    return f"{parent_code}.{sequence}"


def _build_sort_key(*, parent_sort_key: str | None, sequence: int) -> str:
    segment = f"{sequence:0{FinancialGroup.SORT_SEGMENT_WIDTH}d}"
    if parent_sort_key is None:
        return segment
    return f"{parent_sort_key}.{segment}"
