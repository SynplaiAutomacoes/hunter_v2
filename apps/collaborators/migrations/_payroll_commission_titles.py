"""Rewrites payroll commission titles that still carry the internal work order PK."""

from __future__ import annotations

import re
from typing import Any


TITLE_PREFIX = "Comissão OS #"
BATCH_SIZE = 500

_TITLE_PATTERN = re.compile(r"^Comissão OS #(\d+)$")


def parse_title_workorder_pk(title: str) -> int | None:
    match = _TITLE_PATTERN.match((title or "").strip())
    return int(match.group(1)) if match else None


def backfill_commission_item_titles(*, payroll_item_model: Any, workorder_model: Any) -> int:
    items = list(
        payroll_item_model.objects.filter(
            item_type="COMMISSION",
            title__startswith=TITLE_PREFIX,
        ).order_by("pk")
    )
    if not items:
        return 0

    workorder_pk_by_item_pk: dict[int, int] = {}
    for item in items:
        workorder_pk = parse_title_workorder_pk(item.title)
        if workorder_pk is not None:
            workorder_pk_by_item_pk[item.pk] = workorder_pk

    if not workorder_pk_by_item_pk:
        return 0

    public_number_by_workorder_pk: dict[int, int] = {}
    for workorder in workorder_model.objects.filter(pk__in=set(workorder_pk_by_item_pk.values())).select_related("budget"):
        budget = getattr(workorder, "budget", None)
        number = getattr(budget, "number", None) if budget is not None else None
        public_number_by_workorder_pk[workorder.pk] = int(number) if number is not None else int(workorder.pk)

    pending: list[Any] = []
    updated = 0
    for item in items:
        workorder_pk = workorder_pk_by_item_pk.get(item.pk)
        if workorder_pk is None:
            continue
        public_number = public_number_by_workorder_pk.get(workorder_pk)
        if public_number is None:
            continue
        new_title = f"{TITLE_PREFIX}{public_number}"
        if item.title == new_title:
            continue
        item.title = new_title
        pending.append(item)
        updated += 1
        if len(pending) >= BATCH_SIZE:
            payroll_item_model.objects.bulk_update(pending, ["title"])
            pending.clear()

    if pending:
        payroll_item_model.objects.bulk_update(pending, ["title"])

    return updated
