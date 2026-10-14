from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Q
from django.utils import timezone

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

REFERENCE_COPY_DEDUP_WINDOW_SECONDS = 10
REFERENCE_COPY_DEDUP_CACHE_PREFIX = "budget:reference_copy"


def linkable_budgets_q() -> Q:
    """Return a Q filter for budgets eligible to receive a link.

    A budget is linkable when:
    - it has a non-terminal status AND no work-order exists yet, OR
    - it has at least one work-order still open (not delivered, rejected or cancelled).
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


def build_reference_copy_dedup_cache_key(
    *,
    workshop_id: int,
    source_budget_id: int,
    cost_estimator_id: int,
    reference_budget_id: int | None,
) -> str:
    relate_token = "linked" if reference_budget_id is not None else "unlinked"
    return (
        f"{REFERENCE_COPY_DEDUP_CACHE_PREFIX}:{workshop_id}:{source_budget_id}:"
        f"{cost_estimator_id}:{relate_token}"
    )


def remember_reference_copy(
    *,
    workshop_id: int,
    source_budget_id: int,
    cost_estimator_id: int,
    reference_budget_id: int | None,
    copy_budget_id: int,
    within_seconds: int = REFERENCE_COPY_DEDUP_WINDOW_SECONDS,
) -> None:
    cache.set(
        build_reference_copy_dedup_cache_key(
            workshop_id=workshop_id,
            source_budget_id=source_budget_id,
            cost_estimator_id=cost_estimator_id,
            reference_budget_id=reference_budget_id,
        ),
        copy_budget_id,
        timeout=within_seconds,
    )


def find_recent_duplicate_reference_copy(
    *,
    source_budget: Budget,
    cost_estimator_id: int,
    reference_budget_id: int | None,
    within_seconds: int = REFERENCE_COPY_DEDUP_WINDOW_SECONDS,
) -> Budget | None:
    """Return a recent empty copy created by the same user for the same source modal submit.

    Used to make ``BudgetReferenceModalView`` idempotent under double-submit.
    """
    if source_budget.pk is None:
        return None

    cache_key = build_reference_copy_dedup_cache_key(
        workshop_id=int(source_budget.workshop_id),
        source_budget_id=int(source_budget.pk),
        cost_estimator_id=cost_estimator_id,
        reference_budget_id=reference_budget_id,
    )
    cached_pk = cache.get(cache_key)
    if cached_pk is not None:
        cached = (
            Budget.objects.filter(
                pk=cached_pk,
                workshop_id=source_budget.workshop_id,
                cost_estimator_id=cost_estimator_id,
                status__in=NON_TERMINAL_STATUSES,
                reference_budget_id=reference_budget_id,
            )
            .annotate(item_count=Count("items"))
            .filter(item_count=0)
            .first()
        )
        if cached is not None:
            return cached

    # Linked copies are also recoverable from the DB if the cache entry was lost.
    if reference_budget_id is None:
        return None

    cutoff = timezone.now() - timedelta(seconds=within_seconds)
    return (
        Budget.objects.filter(
            workshop_id=source_budget.workshop_id,
            customer_id=source_budget.customer_id,
            vehicle_id=source_budget.vehicle_id,
            cost_estimator_id=cost_estimator_id,
            reference_budget_id=reference_budget_id,
            status__in=NON_TERMINAL_STATUSES,
            criado_em__gte=cutoff,
        )
        .exclude(pk=source_budget.pk)
        .annotate(item_count=Count("items"))
        .filter(item_count=0)
        .order_by("criado_em", "pk")
        .first()
    )
