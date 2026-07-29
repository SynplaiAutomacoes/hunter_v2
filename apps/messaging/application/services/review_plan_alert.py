from __future__ import annotations

import logging
from datetime import datetime

from apps.customer.models import Vehicle
from apps.customer.services.messaging_consent import customer_can_receive_messages
from apps.customer.services.oil_change import notification_run_at_for_vehicle
from apps.messaging.application.services.typed_templates import get_active_template
from apps.messaging.models import MessageTemplate, ScheduledOutboundMessage
from apps.messaging.rendering import render_message_template

logger = logging.getLogger(__name__)


def build_review_plan_alert_message(vehicle: Vehicle) -> str | None:
    template = get_active_template(vehicle.workshop_id, MessageTemplate.TemplateType.REVIEW_PLAN)
    if template is None:
        logger.info(
            "review_plan_alert_skipped_no_active_template",
            extra={"workshop_id": vehicle.workshop_id, "vehicle_id": vehicle.pk},
        )
        return None

    return render_message_template(
        template.message,
        customer=vehicle.customer,
        vehicle=vehicle,
        workshop=vehicle.workshop,
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


def sync_review_plan_alert_schedule(vehicle: Vehicle, *, now: datetime | None = None) -> ScheduledOutboundMessage | None:
    pending_qs = ScheduledOutboundMessage.objects.filter(
        vehicle=vehicle,
        source=ScheduledOutboundMessage.Source.REVIEW_PLAN_ALERT,
        status=ScheduledOutboundMessage.Status.PENDING,
    )

    run_at = notification_run_at_for_vehicle(vehicle, now=now)
    phone = resolve_vehicle_whatsapp_phone(vehicle)
    message = build_review_plan_alert_message(vehicle)
    accepts_messages = customer_can_receive_messages(getattr(vehicle, "customer", None))
    should_schedule = bool(run_at is not None and phone and vehicle.next_oil_change_date and message and accepts_messages)

    if not should_schedule:
        pending_qs.update(status=ScheduledOutboundMessage.Status.CANCELLED)
        return None

    assert run_at is not None
    assert message is not None
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
            source=ScheduledOutboundMessage.Source.REVIEW_PLAN_ALERT,
        )

    existing.customer_id = customer_id
    existing.phone = phone
    existing.message = message
    existing.run_at = run_at
    existing.save(update_fields=["customer_id", "phone", "message", "run_at", "atualizado_em"])
    pending_qs.exclude(pk=existing.pk).update(status=ScheduledOutboundMessage.Status.CANCELLED)
    return existing
