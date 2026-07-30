from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.messaging.models import ScheduledOutboundMessage
from apps.scheduling.models import Appointment, AppointmentStatus


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


def build_appointment_alert_message(appointment: Appointment) -> str:
    starts_local = timezone.localtime(appointment.starts_at).strftime("%d/%m/%Y às %H:%M")
    workshop_name = str(getattr(appointment.workshop, "name", "") or "sua oficina")
    customer_name = appointment.display_customer_name
    return (
        f"Olá {customer_name}! Lembramos do seu agendamento em {workshop_name} "
        f"previsto para {starts_local}. Em caso de dúvidas, fale conosco."
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

    should_schedule = bool(
        appointment.alert_customer
        and appointment.alert_lead_time
        and appointment.status == AppointmentStatus.SCHEDULED
    )

    if not should_schedule:
        pending_qs.update(status=ScheduledOutboundMessage.Status.CANCELLED)
        return None

    run_at = appointment.starts_at - timedelta(minutes=int(appointment.alert_lead_time))
    phone = resolve_appointment_whatsapp_phone(appointment)
    message = build_appointment_alert_message(appointment)
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
