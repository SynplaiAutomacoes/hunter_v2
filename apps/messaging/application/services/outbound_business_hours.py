from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


class OutboundBusinessHoursConfig(Protocol):
    outbound_business_weekdays: str
    outbound_business_start_time: time
    outbound_business_end_time: time


def _parse_weekdays(raw: str) -> frozenset[int]:
    """Parse comma-separated Python weekdays (Mon=0 … Sun=6)."""
    values: set[int] = set()
    for part in str(raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        day = int(part)
        if day < 0 or day > 6:
            raise ValueError(f"Invalid weekday: {day}")
        values.add(day)
    return frozenset(values)


def _workshop_weekdays(workshop: OutboundBusinessHoursConfig) -> frozenset[int]:
    try:
        return _parse_weekdays(str(getattr(workshop, "outbound_business_weekdays", "0,1,2,3,4")))
    except ValueError:
        return frozenset({0, 1, 2, 3, 4})


def _workshop_window_times(workshop: OutboundBusinessHoursConfig) -> tuple[time, time]:
    start = getattr(workshop, "outbound_business_start_time", None) or time(8, 0)
    end = getattr(workshop, "outbound_business_end_time", None) or time(18, 0)
    return start, end


def _local_tz() -> ZoneInfo:
    tz_name = str(getattr(settings, "TIME_ZONE", "America/Sao_Paulo") or "America/Sao_Paulo")
    return ZoneInfo(tz_name)


def is_within_outbound_business_hours(
    workshop: OutboundBusinessHoursConfig,
    moment: datetime | None = None,
) -> bool:
    """
    Return whether outbound appointment alerts may be sent now for a workshop.

    Always respects workshop hours:
    - outbound_business_weekdays (default "0,1,2,3,4" = Mon–Fri)
    - outbound_business_start_time / outbound_business_end_time (default 08:00–18:00, end exclusive)
    Timezone: Django TIME_ZONE (America/Sao_Paulo).
    """
    when = moment or timezone.now()
    local = timezone.localtime(when, _local_tz())
    weekdays = _workshop_weekdays(workshop)

    if local.weekday() not in weekdays:
        return False

    start, end = _workshop_window_times(workshop)
    return start <= local.time() < end


def next_outbound_window_start(
    workshop: OutboundBusinessHoursConfig,
    moment: datetime,
) -> datetime | None:
    """
    Return the first instant >= moment that falls inside the workshop outbound window.

    If moment is already inside the window, return moment itself.
    Scans at most 8 calendar days ahead. Returns None when no weekdays are configured.
    """
    weekdays = _workshop_weekdays(workshop)
    if not weekdays:
        return None

    start, end = _workshop_window_times(workshop)
    if start >= end:
        return None

    tz = _local_tz()
    local = timezone.localtime(moment, tz)

    for day_offset in range(8):
        day = local.date() + timedelta(days=day_offset)
        if day.weekday() not in weekdays:
            continue

        window_open = datetime.combine(day, start, tzinfo=tz)

        if day_offset == 0:
            if start <= local.time() < end:
                return moment
            if local.time() >= end:
                continue
            # Before today's window opens.
            return window_open

        return window_open

    return None
