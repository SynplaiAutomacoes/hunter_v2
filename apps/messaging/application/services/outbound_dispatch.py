from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.customer.services.messaging_consent import blocked_customer_ids
from apps.messaging.application.services.birthday_alert import enqueue_birthday_alerts_for_day
from apps.messaging.application.services.dispatch_history import (
    create_dispatch_batch,
    finalize_batch_after_queue,
    record_queue_failure,
    record_queued_log,
)
from apps.messaging.application.services.outbound_business_hours import is_within_outbound_business_hours
from apps.messaging.application.services.satisfaction_survey import mark_satisfaction_review_sent
from apps.messaging.domain.value_objects import DispatchItem
from apps.messaging.infrastructure.queue.rabbitmq_publisher import RabbitMQPublisher
from apps.messaging.models import MessageDispatchBatch, ScheduledOutboundMessage

logger = logging.getLogger(__name__)

_BATCH_SOURCE_BY_OUTBOUND: dict[str, str] = {
    ScheduledOutboundMessage.Source.REVIEW_PLAN_ALERT: MessageDispatchBatch.Source.REVIEW_PLAN_ALERT,
    ScheduledOutboundMessage.Source.APPOINTMENT_ALERT: MessageDispatchBatch.Source.APPOINTMENT_ALERT,
    ScheduledOutboundMessage.Source.APPOINTMENT_CONFIRMATION: MessageDispatchBatch.Source.APPOINTMENT_CONFIRMATION,
    ScheduledOutboundMessage.Source.BIRTHDAY_ALERT: MessageDispatchBatch.Source.BIRTHDAY_ALERT,
    ScheduledOutboundMessage.Source.SATISFACTION_SURVEY: MessageDispatchBatch.Source.SATISFACTION_SURVEY,
}


def _reschedule_review_plan_alert_if_repeating(row: ScheduledOutboundMessage) -> None:
    if row.source != ScheduledOutboundMessage.Source.REVIEW_PLAN_ALERT:
        return

    vehicle = row.vehicle
    if vehicle is None:
        return

    review_plan = getattr(vehicle, "review_plan", None)
    if review_plan is None or not review_plan.repeat_notification:
        return

    from apps.customer.services.oil_change import reschedule_after_review_plan_alert_sent

    reschedule_after_review_plan_alert_sent(vehicle)


@dataclass(frozen=True, slots=True)
class DueOutboundResult:
    claimed: int
    sent: int
    failed: int
    skipped_outside_hours: bool = False
    birthdays_enqueued: int = 0


def process_due_outbound_messages(*, limit: int = 100, force: bool = False) -> DueOutboundResult:
    now = timezone.now()
    birthdays_enqueued = enqueue_birthday_alerts_for_day(now=now)
    claimed_ids: list[int] = []
    had_due_outside_hours = False

    with transaction.atomic():
        due = list(ScheduledOutboundMessage.objects.select_for_update(skip_locked=True).select_related("workshop").filter(status=ScheduledOutboundMessage.Status.PENDING, run_at__lte=now).order_by("run_at", "pk")[:limit])
        blocked_customers = blocked_customer_ids(row.customer_id for row in due)
        opted_out_ids: list[int] = []
        for row in due:
            if row.customer_id in blocked_customers:
                opted_out_ids.append(row.pk)
                continue
            if force or is_within_outbound_business_hours(row.workshop, moment=now):
                claimed_ids.append(row.pk)
            else:
                had_due_outside_hours = True
        if opted_out_ids:
            ScheduledOutboundMessage.objects.filter(pk__in=opted_out_ids).update(
                status=ScheduledOutboundMessage.Status.CANCELLED,
                atualizado_em=now,
            )
            logger.info("outbound_dispatch_cancelled_customer_opted_out", extra={"cancelled_count": len(opted_out_ids)})
        if claimed_ids:
            ScheduledOutboundMessage.objects.filter(pk__in=claimed_ids).update(
                status=ScheduledOutboundMessage.Status.PROCESSING,
                atualizado_em=now,
            )

    if not claimed_ids:
        return DueOutboundResult(
            claimed=0,
            sent=0,
            failed=0,
            skipped_outside_hours=had_due_outside_hours,
            birthdays_enqueued=birthdays_enqueued,
        )

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
        rows = list(
            ScheduledOutboundMessage.objects.select_related("workshop", "appointment", "vehicle", "vehicle__review_plan").filter(pk__in=claimed_ids)
        )
        for row in rows:
            batch_source = _BATCH_SOURCE_BY_OUTBOUND.get(row.source, MessageDispatchBatch.Source.APPOINTMENT_ALERT)
            batch = create_dispatch_batch(
                workshop_id=row.workshop_id,
                source=batch_source,
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
                mark_satisfaction_review_sent(row)
                _reschedule_review_plan_alert_if_repeating(row)
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

    return DueOutboundResult(
        claimed=len(claimed_ids),
        sent=sent,
        failed=failed,
        birthdays_enqueued=birthdays_enqueued,
    )


def cancel_pending_outbound_for_customer(customer_id: int) -> int:
    """Cancel every pending outbound message of a customer that opted out."""
    cancelled = ScheduledOutboundMessage.objects.filter(
        customer_id=customer_id,
        status=ScheduledOutboundMessage.Status.PENDING,
    ).update(status=ScheduledOutboundMessage.Status.CANCELLED, atualizado_em=timezone.now())
    if cancelled:
        logger.info("outbound_pending_cancelled_customer_opted_out", extra={"customer_id": customer_id, "cancelled_count": cancelled})
    return cancelled


def cancel_pending_outbound_for_customers(customer_ids: list[int]) -> int:
    """Cancel pending outbound messages for many customers at once."""
    if not customer_ids:
        return 0
    cancelled = ScheduledOutboundMessage.objects.filter(
        customer_id__in=customer_ids,
        status=ScheduledOutboundMessage.Status.PENDING,
    ).update(status=ScheduledOutboundMessage.Status.CANCELLED, atualizado_em=timezone.now())
    if cancelled:
        logger.info(
            "outbound_pending_cancelled_customers_opted_out",
            extra={"customer_count": len(customer_ids), "cancelled_count": cancelled},
        )
    return cancelled
