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


ALERT_LEAD_TIME_CHOICES: list[tuple[int, str]] = [
    (30, "30 minutos"),
    (60, "1 hora"),
    (120, "2 horas"),
    (180, "3 horas"),
    (300, "5 horas"),
    (1440, "1 dia"),
    (2880, "2 dias"),
    (10080, "1 semana"),
]


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


def sync_appointment_alert_schedule(appointment: Appointment) -> ScheduledOutboundMessage | None:
    pending_qs = ScheduledOutboundMessage.objects.filter(
        appointment=appointment,
        source=ScheduledOutboundMessage.Source.APPOINTMENT_ALERT,
        status=ScheduledOutboundMessage.Status.PENDING,
    )

    should_schedule = bool(appointment.alert_customer and appointment.alert_lead_time and appointment.status == AppointmentStatus.SCHEDULED)

    # Guests have no Customer record, so there is no toggle to honour for them.
    if should_schedule and appointment.customer_id and not customer_can_receive_messages(appointment.customer):
        should_schedule = False

    if not should_schedule:
        pending_qs.update(status=ScheduledOutboundMessage.Status.CANCELLED)
        return None

    message = build_appointment_alert_message(appointment)
    if not message:
        pending_qs.update(status=ScheduledOutboundMessage.Status.CANCELLED)
        return None

    run_at = appointment.starts_at - timedelta(minutes=int(appointment.alert_lead_time))
    phone = resolve_appointment_whatsapp_phone(appointment)
    if not phone:
        pending_qs.update(status=ScheduledOutboundMessage.Status.CANCELLED)
        return None

    existing = pending_qs.order_by("-criado_em").first()

    if existing is None:
        return ScheduledOutboundMessage.objects.create(
            workshop_id=appointment.workshop_id,
            appointment=appointment,
            customer_id=appointment.customer_id,
            phone=phone,
            message=message,
            run_at=run_at,
            status=ScheduledOutboundMessage.Status.PENDING,
            source=ScheduledOutboundMessage.Source.APPOINTMENT_ALERT,
        )

    existing.customer_id = appointment.customer_id
    existing.phone = phone
    existing.message = message
    existing.run_at = run_at
    existing.save(update_fields=["customer_id", "phone", "message", "run_at", "atualizado_em"])
    pending_qs.exclude(pk=existing.pk).update(status=ScheduledOutboundMessage.Status.CANCELLED)
    return existing
