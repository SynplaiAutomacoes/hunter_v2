from django.db.models import Q

from apps.budget.models import Budget, BudgetStatus
from apps.workorder.models import WORKORDER_OPEN_STATUSES

TERMINAL_STATUSES = {
    BudgetStatus.APPROVED,
    BudgetStatus.REJECTED,
    BudgetStatus.CANCELLED,
}

NON_TERMINAL_STATUSES = tuple(
    status for status in BudgetStatus.values if status not in TERMINAL_STATUSES
)

LINKED_COPY_CLOSED_WORKORDER_MESSAGE = (
    "Não é possível vincular um novo orçamento porque a O.S. está reprovada, cancelada ou com veículo entregue. O orçamento será copiado sem vínculo."
)


def linkable_budgets_q() -> Q:
    """Return a Q filter for budgets eligible to receive a link.

    A budget is linkable when:
    - it has a non-terminal status AND no work-order exists yet, OR
    - it has at least one open work-order.
    """
    return (
        Q(status__in=NON_TERMINAL_STATUSES, workorders__isnull=True)
        | Q(workorders__status__in=WORKORDER_OPEN_STATUSES)
    )


def is_budget_linkable(budget: Budget) -> bool:
    if budget.pk is None:
        return False
    return Budget.objects.filter(linkable_budgets_q(), pk=budget.pk).exists()


def find_oldest_open_budget_for_vehicle(
    workshop_id: int,
    vehicle_id: int,
) -> Budget | None:
    return (
        Budget.objects.filter(
            linkable_budgets_q(),
            workshop_id=workshop_id,
            vehicle_id=vehicle_id,
        )
        .distinct()
        .order_by("criado_em")
        .first()
    )
