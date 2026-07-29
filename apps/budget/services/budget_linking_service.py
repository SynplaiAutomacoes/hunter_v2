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


def find_oldest_open_budget_for_vehicle(
    workshop_id: int,
    vehicle_id: int,
) -> Budget | None:
    budgets_qs = Budget.objects.filter(
        workshop_id=workshop_id,
        vehicle_id=vehicle_id,
        status__in=NON_TERMINAL_STATUSES,
    )

    workorder_budget_ids = (
        WorkOrder.objects.filter(
            workshop_id=workshop_id,
            budget__vehicle_id=vehicle_id,
            status=WorkOrderStatus.DRAFT,
        )
        .values_list("budget_id", flat=True)
        .distinct()
    )

    combined = budgets_qs | Budget.objects.filter(
        pk__in=workorder_budget_ids,
    )

    return combined.distinct().order_by("criado_em").first()
