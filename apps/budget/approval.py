from __future__ import annotations

from django.db import transaction

from apps.budget.models import Budget, BudgetStatus


class BudgetApprovalError(Exception):
    pass


def approve_budget_with_stock(*, budget: Budget, user: object | None = None) -> None:
    blockers = budget.approval_blockers
    if blockers:
        raise BudgetApprovalError(f"Nao e possivel aprovar. {' '.join(blockers)}")

    with transaction.atomic():
        # Budget.save creates the linked work order on approval. Pass the actor
        # explicitly so its immutable author is not confused with a later PDF viewer.
        budget._workorder_created_by = user
        budget.status = BudgetStatus.APPROVED
        budget.save(update_fields=["status"])
