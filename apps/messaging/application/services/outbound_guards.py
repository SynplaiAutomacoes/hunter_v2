from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings

from apps.messaging.application.services.outbound_business_hours import next_outbound_window_start
from apps.messaging.models import ScheduledOutboundMessage
from apps.scheduling.models import AppointmentStatus


def _max_delay() -> timedelta:
    minutes = int(getattr(settings, "OUTBOUND_MAX_DELAY_MINUTES", 15))
    return timedelta(minutes=max(0, minutes))


def appointment_guard_reason(row: ScheduledOutboundMessage, *, now: datetime) -> str:
    """
    Return a cancel reason when an appointment-linked outbound must not be sent.

    Applies to appointment alerts and confirmations only.
    """
    if row.source not in (
        ScheduledOutboundMessage.Source.APPOINTMENT_ALERT,
        ScheduledOutboundMessage.Source.APPOINTMENT_CONFIRMATION,
    ):
        return ""

    appointment = row.appointment
    if appointment is None:
        return ""

    if appointment.status != AppointmentStatus.SCHEDULED:
        return "appointment_not_scheduled"

    if appointment.starts_at <= now:
        return "appointment_started"

    return ""


def staleness_reason(row: ScheduledOutboundMessage, *, now: datetime) -> str:
    """
    Return "stale" when an appointment alert has waited too long past its legal send window.

    Delay is measured from the first moment the row could legally leave (run_at, or the next
    business-hours open if run_at falls outside the window), not from raw run_at alone.
    """
    if row.source != ScheduledOutboundMessage.Source.APPOINTMENT_ALERT:
        return ""

    earliest = next_outbound_window_start(row.workshop, row.run_at) or row.run_at
    if now > earliest + _max_delay():
        return "stale"
    return ""


def outbound_cancel_reason(row: ScheduledOutboundMessage, *, now: datetime) -> str:
    """Return the first applicable cancel reason for a due outbound row, or empty string."""
    reason = appointment_guard_reason(row, now=now)
    if reason:
        return reason
    return staleness_reason(row, now=now)
