from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.budget.models import Budget
from apps.core.domain.services.dashboard_service import DashboardMetrics
from apps.core.infrastructure.models.dashboard_monthly_snapshot import DashboardMonthlySnapshot
from apps.core.infrastructure.services.dashboard_query_service import (
    MONTH_LABELS_PT,
    DashboardQueryService,
    calculate_markup_progress,
    resolve_markup_gauge_tone,
)
from apps.workorder.models import WorkOrder
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop

logger = logging.getLogger(__name__)

SAO_PAULO_TZ = ZoneInfo("America/Sao_Paulo")


def month_close_at(year: int, month: int) -> datetime:
    """Official month close: last calendar day at 23:59:59.999999 in America/Sao_Paulo."""
    last_day = monthrange(year, month)[1]
    return datetime(year, month, last_day, 23, 59, 59, 999999, tzinfo=SAO_PAULO_TZ)


def is_month_closed(year: int, month: int, *, now: datetime | None = None) -> bool:
    current = now if now is not None else timezone.now()
    if timezone.is_naive(current):
        current = timezone.make_aware(current, SAO_PAULO_TZ)
    return current > month_close_at(year, month)


def _as_decimal(value: Any, default: Decimal = Decimal("0.00")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    return value


def iter_activity_months(workshop: Workshop) -> set[tuple[int, int]]:
    """Return (year, month) pairs with any dashboard-relevant activity for the workshop."""
    months: set[tuple[int, int]] = set()

    for year, month in WorkshopCost.objects.filter(workshop=workshop).values_list("year", "month").distinct():
        months.add((int(year), int(month)))

    for entry_date in Budget.objects.filter(workshop=workshop, entry_date__isnull=False).dates("entry_date", "month"):
        months.add((entry_date.year, entry_date.month))

    workorder_qs = WorkOrder.objects.filter(workshop=workshop)
    for created in workorder_qs.dates("criado_em", "month"):
        months.add((created.year, created.month))
    for delivered in workorder_qs.filter(delivered_at__isnull=False).dates("delivered_at", "month"):
        months.add((delivered.year, delivered.month))

    return months


def iter_closed_months_with_activity(workshop: Workshop, *, now: datetime | None = None) -> Iterable[tuple[int, int]]:
    for year, month in sorted(iter_activity_months(workshop)):
        if is_month_closed(year, month, now=now):
            yield year, month


def metrics_field_defaults(metrics: DashboardMetrics) -> dict[str, Any]:
    return {
        "cars_this_month": int(metrics.cars_this_month or 0),
        "warranty_courtesy_cars": int(metrics.warranty_courtesy_cars or 0),
        "average_ticket": _as_decimal(metrics.average_ticket),
        "total_sold_to_date": _as_decimal(metrics.total_sold_to_date),
        "projection": None if metrics.projection is None else _as_decimal(metrics.projection),
        "projection_warning": metrics.projection_warning or "",
        "elapsed_days": int(metrics.elapsed_days or 0),
        "remaining_days": int(metrics.remaining_days or 0),
        "configured_working_days": metrics.configured_working_days,
        "business_holidays": int(metrics.business_holidays or 0),
        "accumulated_profitability": _as_decimal(metrics.accumulated_profitability, Decimal("0")),
        "accumulated_markup": _as_decimal(metrics.accumulated_markup),
        "accumulated_markup_progress": int(metrics.accumulated_markup_progress or 0),
        "warranty_return_rate": _as_decimal(metrics.warranty_return_rate, Decimal("0")),
        "approval_rate": _as_decimal(metrics.approval_rate, Decimal("0")),
        "total_pending_receivable": _as_decimal(metrics.total_pending_receivable),
        "monthly_pending_receivable": _as_decimal(metrics.monthly_pending_receivable),
        "previous_months_pending_receivable": _as_decimal(metrics.previous_months_pending_receivable),
        "total_general_pending_receivable": _as_decimal(metrics.total_general_pending_receivable),
        "total_pending_budgets": _as_decimal(metrics.total_pending_budgets),
        "monthly_pending_budgets": _as_decimal(metrics.monthly_pending_budgets),
        "previous_months_pending_budgets": _as_decimal(metrics.previous_months_pending_budgets),
        "total_general_pending_budgets": _as_decimal(metrics.total_general_pending_budgets),
        "total_rejected_budgets": _as_decimal(metrics.total_rejected_budgets),
        "gross_revenue_target": None if metrics.gross_revenue_target is None else _as_decimal(metrics.gross_revenue_target),
        "daily_revenue_target": None if metrics.daily_revenue_target is None else _as_decimal(metrics.daily_revenue_target),
        "actual_daily_revenue": None if metrics.actual_daily_revenue is None else _as_decimal(metrics.actual_daily_revenue),
        "today_sales": Decimal("0.00"),
        "projection_vs_target": _json_safe(metrics.projection_vs_target) or {},
        "actual_daily_revenue_vs_target": _json_safe(metrics.actual_daily_revenue_vs_target) or {},
    }


def create_snapshot_if_missing(
    workshop: Workshop,
    month: int,
    year: int,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> DashboardMonthlySnapshot:
    """Create an immutable monthly snapshot if one does not exist yet.

    Existing rows are never updated unless ``force=True`` (ops-only escape hatch).
    """
    existing = DashboardMonthlySnapshot.objects.filter(workshop=workshop, year=year, month=month).first()
    if existing is not None and not force:
        return existing

    captured_at = now if now is not None else timezone.now()
    if timezone.is_naive(captured_at):
        captured_at = timezone.make_aware(captured_at, SAO_PAULO_TZ)

    metrics = DashboardQueryService().compute(workshop=workshop, selected_month=month, selected_year=year)
    defaults = metrics_field_defaults(metrics)
    defaults.update(
        {
            "closed_at": month_close_at(year, month),
            "captured_at": captured_at,
        }
    )

    if existing is not None and force:
        for field_name, value in defaults.items():
            setattr(existing, field_name, value)
        existing.save(update_fields=[*defaults.keys(), "atualizado_em"])
        return existing

    snapshot = DashboardMonthlySnapshot.objects.create(workshop=workshop, year=year, month=month, **defaults)
    logger.info(
        "dashboard_monthly_snapshot_created",
        extra={"workshop_id": workshop.pk, "year": year, "month": month, "snapshot_id": snapshot.pk},
    )
    return snapshot


def metrics_from_snapshot(snapshot: DashboardMonthlySnapshot, *, now: datetime | None = None) -> DashboardMetrics:
    """Rebuild DashboardMetrics from a frozen snapshot (empty drill-down lists)."""
    current = now if now is not None else timezone.now()
    if timezone.is_naive(current):
        current = timezone.make_aware(current, SAO_PAULO_TZ)
    local_today: date = timezone.localtime(current, SAO_PAULO_TZ).date()

    workshop_cost = WorkshopCost.objects.filter(
        workshop_id=snapshot.workshop_id,
        month=snapshot.month,
        year=snapshot.year,
    ).first()
    markup_target = workshop_cost.profitability_multiplier if workshop_cost is not None else None
    accumulated_markup = _as_decimal(snapshot.accumulated_markup)

    return DashboardMetrics(
        workshop_id=snapshot.workshop_id,
        selected_month=snapshot.month,
        selected_year=snapshot.year,
        months=[(index, MONTH_LABELS_PT[index]) for index in range(1, 13)],
        years=list(range(local_today.year - 3, local_today.year + 2)),
        cars_this_month=snapshot.cars_this_month,
        cars_this_month_list=[],
        warranty_courtesy_cars=snapshot.warranty_courtesy_cars,
        warranty_courtesy_cars_list=[],
        average_ticket=snapshot.average_ticket,
        projection=snapshot.projection,
        projection_warning=snapshot.projection_warning,
        elapsed_days=snapshot.elapsed_days,
        remaining_days=snapshot.remaining_days,
        configured_working_days=snapshot.configured_working_days,
        business_holidays=snapshot.business_holidays,
        total_sold_to_date=snapshot.total_sold_to_date,
        accumulated_profitability=snapshot.accumulated_profitability,
        accumulated_markup=accumulated_markup,
        accumulated_markup_target=markup_target,
        accumulated_markup_progress=calculate_markup_progress(accumulated_markup, markup_target),
        accumulated_markup_tone=resolve_markup_gauge_tone(accumulated_markup, markup_target),
        warranty_return_rate=snapshot.warranty_return_rate,
        approval_rate=snapshot.approval_rate,
        total_pending_receivable=snapshot.total_pending_receivable,
        total_pending_budgets=snapshot.total_pending_budgets,
        monthly_pending_receivable=snapshot.monthly_pending_receivable,
        total_general_pending_receivable=snapshot.total_general_pending_receivable,
        previous_months_pending_receivable=snapshot.previous_months_pending_receivable,
        total_general_pending_budgets=snapshot.total_general_pending_budgets,
        monthly_pending_budgets=snapshot.monthly_pending_budgets,
        previous_months_pending_budgets=snapshot.previous_months_pending_budgets,
        total_rejected_budgets=snapshot.total_rejected_budgets,
        gross_revenue_target=snapshot.gross_revenue_target,
        daily_revenue_target=snapshot.daily_revenue_target,
        actual_daily_revenue=snapshot.actual_daily_revenue,
        projection_vs_target=snapshot.projection_vs_target or None,
        actual_daily_revenue_vs_target=snapshot.actual_daily_revenue_vs_target or None,
        today_sales=snapshot.today_sales,
    )


def get_dashboard_metrics(
    workshop: Workshop,
    *,
    selected_month: int,
    selected_year: int,
    now: datetime | None = None,
) -> DashboardMetrics:
    """Serve dashboard metrics for the selected month.

    When ``DASHBOARD_USE_MONTHLY_SNAPSHOTS`` is enabled, closed months return the
    frozen snapshot (lazy-creating if missing). Otherwise always compute live.
    """
    from django.conf import settings

    use_snapshots = bool(getattr(settings, "DASHBOARD_USE_MONTHLY_SNAPSHOTS", False))
    if use_snapshots and is_month_closed(selected_year, selected_month, now=now):
        snapshot = create_snapshot_if_missing(workshop, selected_month, selected_year, now=now)
        return metrics_from_snapshot(snapshot, now=now)
    return DashboardQueryService().compute(
        workshop=workshop,
        selected_month=selected_month,
        selected_year=selected_year,
    )


def freeze_due_snapshots(*, now: datetime | None = None, workshop_id: int | None = None) -> int:
    """Create missing snapshots for every closed month with activity. Returns created count."""
    workshops = Workshop.objects.all().order_by("pk")
    if workshop_id is not None:
        workshops = workshops.filter(pk=workshop_id)

    created = 0
    for workshop in workshops.iterator():
        for year, month in iter_closed_months_with_activity(workshop, now=now):
            before_id = (
                DashboardMonthlySnapshot.objects.filter(workshop=workshop, year=year, month=month).values_list("pk", flat=True).first()
            )
            snapshot = create_snapshot_if_missing(workshop, month, year, now=now)
            if before_id is None and snapshot.pk is not None:
                created += 1
    return created


def backfill_closed_snapshots(*, now: datetime | None = None) -> int:
    """Backfill helper used by the data migration and tests."""
    return freeze_due_snapshots(now=now)
