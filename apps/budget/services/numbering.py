from __future__ import annotations

from django.db import transaction

from apps.budget.models import Budget, WorkshopBudgetSequence


@transaction.atomic
def allocate_budget_number(*, workshop_id: int) -> int:
    """Reserve the next free per-workshop budget number.

    Starts from ``last_number + 1`` and skips values already used by the workshop
    (e.g. historical ``number = id`` backfill). Workshops without ``number=1``
    keep ``last_number=0`` so new budgets begin at 1.
    """
    seq = WorkshopBudgetSequence.objects.filter(workshop_id=workshop_id).select_for_update().first()
    if seq is None:
        WorkshopBudgetSequence.objects.get_or_create(workshop_id=workshop_id, defaults={"last_number": 0})
        seq = WorkshopBudgetSequence.objects.select_for_update().get(workshop_id=workshop_id)

    candidate = int(seq.last_number) + 1
    while Budget.objects.filter(workshop_id=workshop_id, number=candidate).exists():
        candidate += 1

    seq.last_number = candidate
    seq.save(update_fields=["last_number"])
    return candidate
