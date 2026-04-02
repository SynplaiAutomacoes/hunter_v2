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
        budget.status = BudgetStatus.APPROVED
        budget.save(update_fields=["status"])
