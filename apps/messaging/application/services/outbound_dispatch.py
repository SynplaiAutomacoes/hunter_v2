from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.messaging.application.services.dispatch_history import (
    create_dispatch_batch,
    finalize_batch_after_queue,
    record_queue_failure,
    record_queued_log,
)
from apps.messaging.application.services.outbound_business_hours import is_within_outbound_business_hours
from apps.messaging.domain.value_objects import DispatchItem
from apps.messaging.infrastructure.queue.rabbitmq_publisher import RabbitMQPublisher
from apps.messaging.models import MessageDispatchBatch, ScheduledOutboundMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DueOutboundResult:
    claimed: int
    sent: int
    failed: int
    skipped_outside_hours: bool = False


def process_due_outbound_messages(*, limit: int = 100, force: bool = False) -> DueOutboundResult:
    if not force and not is_within_outbound_business_hours():
        logger.info("outbound_dispatch_skipped_outside_business_hours")
        return DueOutboundResult(claimed=0, sent=0, failed=0, skipped_outside_hours=True)

    now = timezone.now()
    claimed_ids: list[int] = []

    with transaction.atomic():
        due = (
            ScheduledOutboundMessage.objects.select_for_update(skip_locked=True)
            .filter(status=ScheduledOutboundMessage.Status.PENDING, run_at__lte=now)
            .order_by("run_at", "pk")[:limit]
        )
        for row in due:
            claimed_ids.append(row.pk)
        if claimed_ids:
            ScheduledOutboundMessage.objects.filter(pk__in=claimed_ids).update(
                status=ScheduledOutboundMessage.Status.PROCESSING,
                atualizado_em=now,
            )

    if not claimed_ids:
        return DueOutboundResult(claimed=0, sent=0, failed=0)

    publisher = RabbitMQPublisher(
        host=settings.RABBITMQ_HOST,
        port=settings.RABBITMQ_PORT,
        username=settings.RABBITMQ_USER,
        password=settings.RABBITMQ_PASSWORD,
    )
    sent = 0
    failed = 0
    notified_workshops: dict[int, str] = {}

    try:
        rows = list(ScheduledOutboundMessage.objects.select_related("workshop", "appointment").filter(pk__in=claimed_ids))
        for row in rows:
            batch = create_dispatch_batch(
                workshop_id=row.workshop_id,
                source=MessageDispatchBatch.Source.APPOINTMENT_ALERT,
            )
            customer_id = int(row.customer_id or 0)
            item = DispatchItem(
                group_id=None,
                workshop_id=row.workshop_id,
                customer_id=customer_id,
                phone=row.phone,
                message=row.message,
                client_message_id=str(row.client_message_id),
                batch_id=batch.pk,
            )
            try:
                publisher.publish_dispatch_item(item, workshop_id=row.workshop_id)
                record_queued_log(
                    batch=batch,
                    client_message_id=row.client_message_id,
                    customer_id=row.customer_id or None,
                    phone=row.phone,
                    message=row.message,
                )
                finalize_batch_after_queue(batch)
                row.status = ScheduledOutboundMessage.Status.SENT
                row.batch = batch
                row.error = ""
                row.save(update_fields=["status", "batch", "error", "atualizado_em"])
                instance_name = str(getattr(row.workshop, "whatsapp_instance_name", "") or "")
                notified_workshops[row.workshop_id] = instance_name
                sent += 1
            except Exception as exc:
                logger.exception("outbound_dispatch_failed", extra={"scheduled_id": row.pk})
                record_queue_failure(
                    batch=batch,
                    client_message_id=row.client_message_id,
                    customer_id=row.customer_id,
                    phone=row.phone,
                    message=row.message,
                    error=str(exc),
                )
                finalize_batch_after_queue(batch)
                row.status = ScheduledOutboundMessage.Status.FAILED
                row.batch = batch
                row.error = str(exc)
                row.save(update_fields=["status", "batch", "error", "atualizado_em"])
                failed += 1

        for workshop_id, instance_name in notified_workshops.items():
            publisher.publish_workshop_control(workshop_id, whatsapp_instance_name=instance_name)
    finally:
        publisher.close()

    return DueOutboundResult(claimed=len(claimed_ids), sent=sent, failed=failed)
