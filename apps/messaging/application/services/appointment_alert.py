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


def _first_name(full_name: str) -> str:
    name = str(full_name or "").strip()
    if not name:
        return ""
    return name.split(None, 1)[0]


def build_appointment_message_extras(appointment: Appointment) -> dict[str, str]:
    starts_local = timezone.localtime(appointment.starts_at)
    extras: dict[str, str] = {
        "data_agendamento": starts_local.strftime("%d/%m/%Y"),
        "hora_agendamento": starts_local.strftime("%H:%M"),
    }
    if getattr(appointment, "customer_id", None):
        return extras

    full_name = appointment.display_customer_name
    extras["nome"] = full_name
    extras["primeiro_nome"] = _first_name(full_name)

    phone = str(appointment.guest_customer_phone or "").strip()
    if phone:
        extras["telefone"] = phone

    cpf = str(appointment.display_customer_cpf or "").strip()
    if cpf:
        extras["cpf"] = cpf

    guest_vehicle_values = {
        "placa": appointment.guest_vehicle_plate,
        "marca": appointment.guest_vehicle_brand,
        "modelo": appointment.guest_vehicle_model,
        "ano_fabricacao": appointment.guest_vehicle_year_fabrication,
        "ano_modelo": appointment.guest_vehicle_year_model,
        "motorizacao": appointment.guest_vehicle_engine,
        "combustivel": appointment.guest_vehicle_fuel,
    }
    for key, value in guest_vehicle_values.items():
        text = str(value or "").strip()
        if text:
            extras[key] = text
    return extras


def build_appointment_typed_message(appointment: Appointment, template_type: str) -> str | None:
    template = get_active_template(appointment.workshop_id, template_type)
    if template is None:
        logger.info(
            "appointment_message_skipped_no_active_template",
            extra={
                "workshop_id": appointment.workshop_id,
                "appointment_id": appointment.pk,
                "template_type": template_type,
            },
        )
        return None

    return render_message_template(
        template.message,
        customer=appointment.customer,
        workshop=appointment.workshop,
        appointment=appointment,
        extras=build_appointment_message_extras(appointment),
    )


def build_appointment_alert_message(appointment: Appointment) -> str | None:
    return build_appointment_typed_message(appointment, MessageTemplate.TemplateType.APPOINTMENT)


def refresh_appointment_alert_message(row: ScheduledOutboundMessage) -> bool:
    """Re-render a pending/claimed alert from the workshop's current APPOINTMENT template."""
    if row.source != ScheduledOutboundMessage.Source.APPOINTMENT_ALERT:
        return False
    appointment = row.appointment
    if appointment is None:
        return False

    message = build_appointment_alert_message(appointment)
    if not message or row.message == message:
        return False

    row.message = message
    row.save(update_fields=["message", "atualizado_em"])
    return True


def refresh_pending_appointment_alerts_for_workshop(workshop_id: int) -> int:
    """Update all PENDING appointment alerts for a workshop with the active template text."""
    rows = ScheduledOutboundMessage.objects.filter(
        workshop_id=workshop_id,
        source=ScheduledOutboundMessage.Source.APPOINTMENT_ALERT,
        status=ScheduledOutboundMessage.Status.PENDING,
        appointment__isnull=False,
    ).select_related("appointment", "appointment__customer", "appointment__workshop", "workshop")
    updated = 0
    for row in rows:
        if refresh_appointment_alert_message(row):
            updated += 1
    if updated:
        logger.info(
            "appointment_alert_messages_refreshed_from_template",
            extra={"workshop_id": workshop_id, "updated_count": updated},
        )
    return updated


def resolve_appointment_whatsapp_phone(appointment: Appointment) -> str:
    # Same as message-group dispatch: PhoneNumber.as_e164 without leading '+'.
    if getattr(appointment, "customer_id", None) and appointment.customer and appointment.customer.phone:
        return str(appointment.customer.phone.as_e164).lstrip("+")
    guest_phone = appointment.guest_customer_phone
    if guest_phone:
        return str(guest_phone.as_e164).lstrip("+")
    return ""


def enqueue_appointment_confirmation(appointment: Appointment) -> ScheduledOutboundMessage | None:
    """Queue an immediate confirmation message when a new appointment is created."""
    if appointment.status != AppointmentStatus.SCHEDULED:
        return None

    if appointment.customer_id and not customer_can_receive_messages(appointment.customer):
        return None

    existing = (
        ScheduledOutboundMessage.objects.filter(
            appointment=appointment,
            source=ScheduledOutboundMessage.Source.APPOINTMENT_CONFIRMATION,
            status__in=(
                ScheduledOutboundMessage.Status.PENDING,
                ScheduledOutboundMessage.Status.PROCESSING,
            ),
        )
        .order_by("-criado_em")
        .first()
    )
    if existing is not None:
        return existing

    message = build_appointment_typed_message(appointment, MessageTemplate.TemplateType.APPOINTMENT_CONFIRMATION)
    if not message:
        return None

    phone = resolve_appointment_whatsapp_phone(appointment)
    if not phone:
        return None

    return ScheduledOutboundMessage.objects.create(
        workshop_id=appointment.workshop_id,
        appointment=appointment,
        customer_id=appointment.customer_id,
        phone=phone,
        message=message,
        run_at=timezone.now(),
        status=ScheduledOutboundMessage.Status.PENDING,
        source=ScheduledOutboundMessage.Source.APPOINTMENT_CONFIRMATION,
    )


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

    now = timezone.now()
    desired_run_ats = {appointment.starts_at - timedelta(minutes=lead_minutes): lead_minutes for lead_minutes in lead_times}
    existing_by_run_at = {row.run_at: row for row in pending_qs.order_by("-criado_em")}
    kept_ids: list[int] = []
    result: list[ScheduledOutboundMessage] = []

    for run_at in desired_run_ats:
        # Do not compensate for lead times whose send window already passed.
        if run_at <= now:
            continue

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
