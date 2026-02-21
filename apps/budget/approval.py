from __future__ import annotations

from django.db import transaction

from apps.budget.models import Budget, BudgetStatus


class BudgetApprovalError(Exception):
    pass


def approve_budget_with_stock(*, budget: Budget, user=None) -> None:
    local_items = budget.items.filter(is_local=True)
    if local_items.exists():
        raise BudgetApprovalError("Nao e possivel aprovar. Existem itens sem cadastro (locais).")

    with transaction.atomic():
        budget.status = BudgetStatus.APPROVED
        budget.save(update_fields=["status"])
