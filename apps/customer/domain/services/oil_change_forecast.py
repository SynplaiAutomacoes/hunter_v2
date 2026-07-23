from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal


MAX_PLAUSIBLE_KM_PER_DAY = Decimal("2000")


@dataclass(frozen=True, slots=True)
class MileageReadingPoint:
    read_at: date
    odometer_km: int


@dataclass(frozen=True, slots=True)
class OilChangeForecast:
    limit_by_days: date
    limit_by_km: date | None
    next_change_date: date
    reason: str
    daily_km_average: Decimal | None
    km_limit: int
    is_expired: bool


def compute_daily_km_average(readings: list[MileageReadingPoint]) -> Decimal | None:
    """Average daily km from ordered mileage readings, ignoring invalid segments."""
    if len(readings) < 2:
        return None

    ordered = sorted(readings, key=lambda item: (item.read_at, item.odometer_km))
    total_km = Decimal("0")
    total_days = Decimal("0")
    previous: MileageReadingPoint | None = None

    for current in ordered:
        if current.odometer_km < 0:
            continue
        if previous is None:
            previous = current
            continue

        days = (current.read_at - previous.read_at).days
        km_delta = current.odometer_km - previous.odometer_km

        if days <= 0:
            previous = current if current.odometer_km >= previous.odometer_km else previous
            continue
        if km_delta < 0:
            continue
        if km_delta == 0 and current.read_at == previous.read_at:
            continue

        km_per_day = Decimal(km_delta) / Decimal(days)
        if km_per_day > MAX_PLAUSIBLE_KM_PER_DAY:
            previous = current
            continue

        total_km += Decimal(km_delta)
        total_days += Decimal(days)
        previous = current

    if total_days <= 0 or total_km < 0:
        return None
    return total_km / total_days


def compute_oil_change_forecast(
    *,
    last_oil_change_date: date,
    last_oil_change_km: int,
    validity_days: int,
    validity_km: int,
    current_km: int | None,
    today: date,
    daily_km_average: Decimal | None,
) -> OilChangeForecast:
    limit_by_days = last_oil_change_date + timedelta(days=validity_days)
    km_limit = last_oil_change_km + validity_km

    limit_by_km: date | None = None
    if daily_km_average is not None and daily_km_average > 0 and current_km is not None:
        remaining_km = Decimal(km_limit - current_km)
        days_remaining = remaining_km / daily_km_average
        rounding = ROUND_FLOOR if days_remaining < 0 else ROUND_HALF_UP
        whole_days = int(days_remaining.to_integral_value(rounding=rounding))
        limit_by_km = today + timedelta(days=whole_days)

    if limit_by_km is None:
        next_change_date = limit_by_days
        reason = "VALIDADE_POR_DIAS"
    elif limit_by_days <= limit_by_km:
        next_change_date = limit_by_days
        reason = "VALIDADE_POR_DIAS"
    else:
        next_change_date = limit_by_km
        reason = "VALIDADE_POR_QUILOMETRAGEM"

    is_expired = today >= limit_by_days or (current_km is not None and current_km >= km_limit)
    return OilChangeForecast(
        limit_by_days=limit_by_days,
        limit_by_km=limit_by_km,
        next_change_date=next_change_date,
        reason=reason,
        daily_km_average=daily_km_average,
        km_limit=km_limit,
        is_expired=is_expired,
    )
