from __future__ import annotations

from datetime import datetime, time
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
    tz_name = str(getattr(settings, "TIME_ZONE", "America/Sao_Paulo") or "America/Sao_Paulo")
    local = timezone.localtime(when, ZoneInfo(tz_name))

    try:
        weekdays = _parse_weekdays(str(getattr(workshop, "outbound_business_weekdays", "0,1,2,3,4")))
    except ValueError:
        weekdays = frozenset({0, 1, 2, 3, 4})

    if local.weekday() not in weekdays:
        return False

    start = getattr(workshop, "outbound_business_start_time", None) or time(8, 0)
    end = getattr(workshop, "outbound_business_end_time", None) or time(18, 0)
    return start <= local.time() < end
