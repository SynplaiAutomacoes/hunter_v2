from __future__ import annotations

from datetime import datetime

from apps.customer.models import Vehicle
from apps.customer.services.oil_change import notification_run_at_for_vehicle
from apps.messaging.models import ScheduledOutboundMessage


def build_oil_change_alert_message(vehicle: Vehicle) -> str:
    workshop_name = str(getattr(vehicle.workshop, "name", "") or "sua oficina")
    customer_name = str(getattr(vehicle.customer, "name", "") or "cliente")
    plate = vehicle.plate or "seu veículo"
    next_date = vehicle.next_oil_change_date
    next_date_display = next_date.strftime("%d/%m/%Y") if next_date else "em breve"
    return (
        f"Olá {customer_name}! Lembramos que a troca de óleo do veículo {plate} "
        f"está prevista para {next_date_display}. Em caso de dúvidas, fale com {workshop_name}."
    )


def resolve_vehicle_whatsapp_phone(vehicle: Vehicle) -> str:
    customer = getattr(vehicle, "customer", None)
    phone = getattr(customer, "phone", None) if customer is not None else None
    if phone is None:
        return ""
    as_e164 = getattr(phone, "as_e164", None)
    if not as_e164:
        return ""
    return str(as_e164).lstrip("+")


def sync_oil_change_alert_schedule(vehicle: Vehicle, *, now: datetime | None = None) -> ScheduledOutboundMessage | None:
    pending_qs = ScheduledOutboundMessage.objects.filter(
        vehicle=vehicle,
        source=ScheduledOutboundMessage.Source.OIL_CHANGE_ALERT,
        status=ScheduledOutboundMessage.Status.PENDING,
    )

    run_at = notification_run_at_for_vehicle(vehicle, now=now)
    phone = resolve_vehicle_whatsapp_phone(vehicle)
    should_schedule = bool(run_at is not None and phone and vehicle.next_oil_change_date)

    if not should_schedule:
        pending_qs.update(status=ScheduledOutboundMessage.Status.CANCELLED)
        return None

    assert run_at is not None
    message = build_oil_change_alert_message(vehicle)
    existing = pending_qs.order_by("-criado_em").first()
    customer_id = vehicle.customer_id

    if existing is None:
        return ScheduledOutboundMessage.objects.create(
            workshop_id=vehicle.workshop_id,
            vehicle=vehicle,
            customer_id=customer_id,
            phone=phone,
            message=message,
            run_at=run_at,
            status=ScheduledOutboundMessage.Status.PENDING,
            source=ScheduledOutboundMessage.Source.OIL_CHANGE_ALERT,
        )

    existing.customer_id = customer_id
    existing.phone = phone
    existing.message = message
    existing.run_at = run_at
    existing.save(update_fields=["customer_id", "phone", "message", "run_at", "atualizado_em"])
    pending_qs.exclude(pk=existing.pk).update(status=ScheduledOutboundMessage.Status.CANCELLED)
    return existing
