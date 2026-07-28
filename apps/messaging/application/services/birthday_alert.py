from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time

from django.db.models import Q
from django.utils import timezone

from apps.customer.models import Customer
from apps.messaging.application.services.typed_templates import get_active_template
from apps.messaging.models import MessageTemplate, ScheduledOutboundMessage
from apps.messaging.rendering import render_message_template
from apps.workshops.models.workshops import Workshop

logger = logging.getLogger(__name__)


def birthday_client_message_id(customer_id: int, year: int) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"birthday:{customer_id}:{year}")


def resolve_customer_whatsapp_phone(customer: Customer) -> str:
    phone = getattr(customer, "phone", None)
    if phone is None:
        return ""
    as_e164 = getattr(phone, "as_e164", None)
    if not as_e164:
        return ""
    return str(as_e164).lstrip("+")


def build_birthday_alert_message(*, customer: Customer, workshop: Workshop, template: MessageTemplate) -> str:
    return render_message_template(
        template.message,
        customer=customer,
        workshop=workshop,
    )


def enqueue_birthday_alerts_for_day(*, target_date: date | None = None, now: datetime | None = None) -> int:
    """Create pending birthday outbound messages for customers whose birthday is today."""
    moment = now or timezone.now()
    today = target_date or timezone.localdate(moment)
    year = today.year
    created = 0

    workshops = Workshop.objects.filter(is_active=True).only("id", "name")
    for workshop in workshops:
        template = get_active_template(workshop.pk, MessageTemplate.TemplateType.BIRTHDAY)
        if template is None:
            continue

        customers = (
            Customer.objects.filter(
                workshop_id=workshop.pk,
                is_active=True,
                birth_date__month=today.month,
                birth_date__day=today.day,
            )
            .exclude(Q(phone__isnull=True) | Q(phone=""))
            .iterator()
        )

        for customer in customers:
            phone = resolve_customer_whatsapp_phone(customer)
            if not phone:
                continue

            client_message_id = birthday_client_message_id(customer.pk, year)
            already_exists = (
                ScheduledOutboundMessage.objects.filter(
                    client_message_id=client_message_id,
                )
                .exclude(status=ScheduledOutboundMessage.Status.CANCELLED)
                .exists()
            )
            if already_exists:
                continue

            message = build_birthday_alert_message(customer=customer, workshop=workshop, template=template)
            run_at = timezone.make_aware(datetime.combine(today, time(9, 0)))
            if run_at < moment:
                run_at = moment

            ScheduledOutboundMessage.objects.create(
                workshop_id=workshop.pk,
                customer_id=customer.pk,
                phone=phone,
                message=message,
                run_at=run_at,
                status=ScheduledOutboundMessage.Status.PENDING,
                source=ScheduledOutboundMessage.Source.BIRTHDAY_ALERT,
                client_message_id=client_message_id,
            )
            created += 1

    if created:
        logger.info("birthday_alerts_enqueued", extra={"enqueued_count": created, "date": today.isoformat()})
    return created
