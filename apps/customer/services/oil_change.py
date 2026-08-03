from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from apps.customer.domain.services.oil_change_forecast import (
    MileageReadingPoint,
    OilChangeForecast,
    compute_daily_km_average,
    compute_oil_change_forecast,
)
from apps.customer.models import (
    MileageReadingSource,
    Vehicle,
    VehicleMileageReading,
    VehicleOilChange,
)

if TYPE_CHECKING:
    from apps.budget.models import Budget
    from apps.workorder.models import WorkOrder
    from apps.workshops.models.review_plans import ReviewPlan


def _local_today() -> date:
    return timezone.localdate()


def _readings_for_vehicle(vehicle: Vehicle) -> list[MileageReadingPoint]:
    rows = VehicleMileageReading.objects.filter(vehicle=vehicle).order_by("read_at", "odometer_km", "pk")
    return [MileageReadingPoint(read_at=row.read_at, odometer_km=row.odometer_km) for row in rows]


def build_vehicle_oil_forecast(vehicle: Vehicle, *, today: date | None = None) -> OilChangeForecast | None:
    if vehicle.last_oil_change_date is None or vehicle.last_oil_change_km is None or vehicle.review_plan_id is None:
        return None

    review_plan = vehicle.review_plan
    if review_plan is None:
        return None

    effective_today = today or _local_today()
    daily_average = compute_daily_km_average(_readings_for_vehicle(vehicle))
    return compute_oil_change_forecast(
        last_oil_change_date=vehicle.last_oil_change_date,
        last_oil_change_km=vehicle.last_oil_change_km,
        validity_days=review_plan.validity_days,
        validity_km=review_plan.validity_km,
        current_km=vehicle.km,
        today=effective_today,
        daily_km_average=daily_average,
    )


def apply_forecast_to_vehicle(vehicle: Vehicle, forecast: OilChangeForecast | None) -> Vehicle:
    if forecast is None:
        vehicle.next_oil_change_date = None
        vehicle.oil_forecast_reason = None
    else:
        vehicle.next_oil_change_date = forecast.next_change_date
        vehicle.oil_forecast_reason = forecast.reason
    vehicle.save(update_fields=["next_oil_change_date", "oil_forecast_reason", "atualizado_em"])
    return vehicle


def recalculate_and_sync_oil_alert(vehicle: Vehicle) -> OilChangeForecast | None:
    forecast = build_vehicle_oil_forecast(vehicle)
    apply_forecast_to_vehicle(vehicle, forecast)
    from apps.messaging.application.services.review_plan_alert import sync_review_plan_alert_schedule

    sync_review_plan_alert_schedule(vehicle)
    return forecast


def reschedule_after_review_plan_alert_sent(vehicle: Vehicle) -> OilChangeForecast | None:
    """Advance the next reminder window and reschedule after a review-plan alert is sent.

    Used when the review plan has `repeat_notification` enabled and no new oil change was
    recorded yet. Advances `next_oil_change_date` by another `validity_days` period from
    the current next date (or today if already past), then overwrites the pending alert
    so the customer is notified again. Once a real `VehicleOilChange` is recorded, the
    forecast is recalculated from fresh data and this loop naturally stops.
    """
    review_plan = vehicle.review_plan
    if review_plan is None or not review_plan.repeat_notification:
        return None

    today = _local_today()
    base = vehicle.next_oil_change_date or today
    if base < today:
        base = today
    vehicle.next_oil_change_date = base + timedelta(days=int(review_plan.validity_days))
    vehicle.save(update_fields=["next_oil_change_date", "atualizado_em"])

    from apps.messaging.application.services.review_plan_alert import sync_review_plan_alert_schedule

    sync_review_plan_alert_schedule(vehicle)
    return build_vehicle_oil_forecast(vehicle)


def record_mileage_reading(
    *,
    vehicle: Vehicle,
    odometer_km: int,
    read_at: date,
    source: str,
    budget: Budget | None = None,
    workorder: WorkOrder | None = None,
    update_vehicle_km: bool = True,
) -> VehicleMileageReading:
    reading = VehicleMileageReading.objects.create(
        vehicle=vehicle,
        read_at=read_at,
        odometer_km=odometer_km,
        source=source,
        budget=budget,
        workorder=workorder,
    )
    if update_vehicle_km and (vehicle.km is None or odometer_km > vehicle.km):
        vehicle.km = odometer_km
        vehicle.save(update_fields=["km", "atualizado_em"])
    return reading


def record_oil_change_from_workorder_delivery(*, workorder: WorkOrder) -> VehicleOilChange | None:
    budget = workorder.budget
    vehicle = getattr(budget, "vehicle", None) if budget is not None else None
    if vehicle is None:
        return None

    has_oil_change = bool(workorder.last_oil_change_date and workorder.last_oil_change_km is not None and workorder.review_plan_id)
    if not has_oil_change:
        return None

    existing = VehicleOilChange.objects.filter(workorder=workorder).first()
    if existing is not None:
        return existing

    review_plan = workorder.review_plan
    if review_plan is None:
        return None

    oil_change = VehicleOilChange.objects.create(
        vehicle=vehicle,
        changed_at=workorder.last_oil_change_date,
        odometer_km=int(workorder.last_oil_change_km),
        review_plan=review_plan,
        validity_days=review_plan.validity_days,
        validity_km=review_plan.validity_km,
        budget=budget,
        workorder=workorder,
    )
    vehicle.last_oil_change_date = oil_change.changed_at
    vehicle.last_oil_change_km = oil_change.odometer_km
    vehicle.review_plan = review_plan
    vehicle.save(update_fields=["last_oil_change_date", "last_oil_change_km", "review_plan", "atualizado_em"])
    return oil_change


@transaction.atomic
def handle_workorder_delivery_oil_and_mileage(*, workorder: WorkOrder) -> None:
    budget = workorder.budget
    vehicle = getattr(budget, "vehicle", None) if budget is not None else None
    if vehicle is None:
        return

    km_final = workorder.km_final
    if km_final is not None:
        read_at = timezone.localdate(workorder.delivered_at) if workorder.delivered_at else _local_today()
        already_recorded = VehicleMileageReading.objects.filter(
            workorder=workorder,
            source=MileageReadingSource.WORKORDER_DELIVERY,
        ).exists()
        if not already_recorded:
            record_mileage_reading(
                vehicle=vehicle,
                odometer_km=km_final,
                read_at=read_at,
                source=MileageReadingSource.WORKORDER_DELIVERY,
                budget=budget,
                workorder=workorder,
                update_vehicle_km=True,
            )

    record_oil_change_from_workorder_delivery(workorder=workorder)
    vehicle.refresh_from_db()
    recalculate_and_sync_oil_alert(vehicle)


@transaction.atomic
def handle_budget_approved_mileage(*, budget: Budget) -> None:
    vehicle = budget.vehicle
    if vehicle is None or budget.current_km is None:
        return

    if vehicle.km != budget.current_km:
        vehicle.km = budget.current_km
        vehicle.save(update_fields=["km", "atualizado_em"])

    record_mileage_reading(
        vehicle=vehicle,
        odometer_km=budget.current_km,
        read_at=budget.entry_date or _local_today(),
        source=MileageReadingSource.BUDGET,
        budget=budget,
        update_vehicle_km=False,
    )
    vehicle.refresh_from_db()
    if vehicle.review_plan_id and vehicle.last_oil_change_date and vehicle.last_oil_change_km is not None:
        recalculate_and_sync_oil_alert(vehicle)


def recalculate_oil_forecasts_for_review_plan(*, review_plan: ReviewPlan) -> None:
    vehicles = Vehicle.objects.filter(review_plan=review_plan).select_related("review_plan", "customer")
    for vehicle in vehicles.iterator():
        recalculate_and_sync_oil_alert(vehicle)


def notification_run_at_for_vehicle(vehicle: Vehicle, *, now: datetime | None = None) -> datetime | None:
    if vehicle.next_oil_change_date is None or vehicle.review_plan_id is None or vehicle.review_plan is None:
        return None

    current = now or timezone.now()
    lead_days = int(vehicle.review_plan.notification_lead_days)
    trigger_date = vehicle.next_oil_change_date - timedelta(days=lead_days)
    local_tz = timezone.get_current_timezone()
    run_at = timezone.make_aware(datetime.combine(trigger_date, time.min), local_tz)
    if run_at <= current:
        return current
    return run_at
