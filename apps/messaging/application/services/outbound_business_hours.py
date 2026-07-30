from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


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


def is_within_outbound_business_hours(moment: datetime | None = None) -> bool:
    """
    Return whether outbound appointment alerts may be sent now.

    Controlled by settings (env):
    - OUTBOUND_BUSINESS_HOURS_ENABLED (default True)
    - OUTBOUND_BUSINESS_WEEKDAYS (default "0,1,2,3,4" = Mon–Fri)
    - OUTBOUND_BUSINESS_START_HOUR / OUTBOUND_BUSINESS_END_HOUR (default 8–18, end exclusive)
    Timezone: Django TIME_ZONE (America/Sao_Paulo).
    """
    if not getattr(settings, "OUTBOUND_BUSINESS_HOURS_ENABLED", True):
        return True

    when = moment or timezone.now()
    tz_name = str(getattr(settings, "TIME_ZONE", "America/Sao_Paulo") or "America/Sao_Paulo")
    local = timezone.localtime(when, ZoneInfo(tz_name))

    try:
        weekdays = _parse_weekdays(str(getattr(settings, "OUTBOUND_BUSINESS_WEEKDAYS", "0,1,2,3,4")))
    except ValueError:
        weekdays = frozenset({0, 1, 2, 3, 4})

    if local.weekday() not in weekdays:
        return False

    start_hour = int(getattr(settings, "OUTBOUND_BUSINESS_START_HOUR", 8))
    end_hour = int(getattr(settings, "OUTBOUND_BUSINESS_END_HOUR", 18))
    start = time(hour=max(0, min(start_hour, 23)))
    end = time(hour=max(0, min(end_hour, 23)))
    return start <= local.time() < end
