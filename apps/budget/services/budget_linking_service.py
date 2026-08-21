from django.db.models import Q

from apps.budget.models import Budget, BudgetStatus
from apps.workorder.models import WorkOrder, WorkOrderStatus

TERMINAL_STATUSES = {
    BudgetStatus.APPROVED,
    BudgetStatus.REJECTED,
    BudgetStatus.CANCELLED,
}

NON_TERMINAL_STATUSES = tuple(
    status for status in BudgetStatus.values if status not in TERMINAL_STATUSES
)


def linkable_budgets_q() -> Q:
    """Return a Q filter for budgets eligible to receive a link.

    A budget is linkable when:
    - it has a non-terminal status AND no work-order exists yet, OR
    - it has at least one open work-order (status=DRAFT).
    """
    return (
        Q(status__in=NON_TERMINAL_STATUSES, workorders__isnull=True)
        | Q(workorders__status=WorkOrderStatus.DRAFT)
    )


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
