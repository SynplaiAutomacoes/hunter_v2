from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from apps.customer.services.messaging_consent import customer_can_receive_messages
from apps.messaging.application.services.typed_templates import get_active_template
from apps.messaging.models import MessageTemplate, ScheduledOutboundMessage
from apps.messaging.rendering import render_message_template
from apps.scheduling.models import Appointment, AppointmentStatus

logger = logging.getLogger(__name__)


def build_appointment_alert_message(appointment: Appointment) -> str | None:
    template = get_active_template(appointment.workshop_id, MessageTemplate.TemplateType.APPOINTMENT)
    if template is None:
        logger.info(
            "appointment_alert_skipped_no_active_template",
            extra={"workshop_id": appointment.workshop_id, "appointment_id": appointment.pk},
        )
        return None

    starts_local = timezone.localtime(appointment.starts_at)
    customer = appointment.customer
    extras: dict[str, str] = {
        "data_agendamento": starts_local.strftime("%d/%m/%Y"),
        "hora_agendamento": starts_local.strftime("%H:%M"),
    }
    if customer is None:
        extras["nome"] = appointment.display_customer_name
    return render_message_template(
        template.message,
        customer=customer,
        workshop=appointment.workshop,
        extras=extras,
    )


def resolve_appointment_whatsapp_phone(appointment: Appointment) -> str:
    # Same as message-group dispatch: PhoneNumber.as_e164 without leading '+'.
    if getattr(appointment, "customer_id", None) and appointment.customer and appointment.customer.phone:
        return appointment.customer.phone.as_e164.lstrip("+")
    guest_phone = appointment.guest_customer_phone
    if guest_phone:
        return guest_phone.as_e164.lstrip("+")
    return ""


def sync_appointment_alert_schedule(appointment: Appointment) -> list[ScheduledOutboundMessage]:
    """Create/update one pending outbound message per selected alert lead time."""
    pending_qs = ScheduledOutboundMessage.objects.filter(
        appointment=appointment,
        source=ScheduledOutboundMessage.Source.APPOINTMENT_ALERT,
        status=ScheduledOutboundMessage.Status.PENDING,
    )

    lead_times = [int(value) for value in (appointment.alert_lead_times or []) if value]
    should_schedule = bool(appointment.alert_customer and lead_times and appointment.status == AppointmentStatus.SCHEDULED)

    # Guests have no Customer record, so there is no toggle to honour for them.
    if should_schedule and appointment.customer_id and not customer_can_receive_messages(appointment.customer):
        should_schedule = False

    if not should_schedule:
        pending_qs.update(status=ScheduledOutboundMessage.Status.CANCELLED)
        return []

    message = build_appointment_alert_message(appointment)
    if not message:
        pending_qs.update(status=ScheduledOutboundMessage.Status.CANCELLED)
        return []

    phone = resolve_appointment_whatsapp_phone(appointment)
    if not phone:
        pending_qs.update(status=ScheduledOutboundMessage.Status.CANCELLED)
        return []

    desired_run_ats = {appointment.starts_at - timedelta(minutes=lead_minutes): lead_minutes for lead_minutes in lead_times}
    existing_by_run_at = {row.run_at: row for row in pending_qs.order_by("-criado_em")}
    kept_ids: list[int] = []
    result: list[ScheduledOutboundMessage] = []

    for run_at in desired_run_ats:
        existing = existing_by_run_at.get(run_at)
        if existing is None:
            existing = ScheduledOutboundMessage.objects.create(
                workshop_id=appointment.workshop_id,
                appointment=appointment,
                customer_id=appointment.customer_id,
                phone=phone,
                message=message,
                run_at=run_at,
                status=ScheduledOutboundMessage.Status.PENDING,
                source=ScheduledOutboundMessage.Source.APPOINTMENT_ALERT,
            )
        else:
            existing.customer_id = appointment.customer_id
            existing.phone = phone
            existing.message = message
            existing.run_at = run_at
            existing.save(update_fields=["customer_id", "phone", "message", "run_at", "atualizado_em"])
        kept_ids.append(existing.pk)
        result.append(existing)

    pending_qs.exclude(pk__in=kept_ids).update(status=ScheduledOutboundMessage.Status.CANCELLED)
    return result
