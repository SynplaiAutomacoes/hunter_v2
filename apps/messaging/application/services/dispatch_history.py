from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.messaging.models import MessageDispatchBatch, MessageDispatchLog


def create_dispatch_batch(
    *,
    workshop_id: int,
    source: str,
    group_id: int | None = None,
    triggered_by_id: int | None = None,
) -> MessageDispatchBatch:
    return MessageDispatchBatch.objects.create(
        workshop_id=workshop_id,
        group_id=group_id,
        source=source,
        triggered_by_id=triggered_by_id,
        status=MessageDispatchBatch.Status.QUEUED,
    )


def resolve_client_message_id(
    *,
    customer_id: int,
    client_message_ids: Mapping[int, str] | None,
) -> UUID:
    if client_message_ids:
        raw = client_message_ids.get(customer_id)
        if raw:
            return UUID(str(raw))
    return uuid4()


def record_queued_log(
    *,
    batch: MessageDispatchBatch,
    client_message_id: UUID,
    customer_id: int | None,
    phone: str,
    message: str,
) -> MessageDispatchLog:
    log = MessageDispatchLog.objects.create(
        batch=batch,
        client_message_id=client_message_id,
        customer_id=customer_id,
        phone=phone,
        message=message,
        status=MessageDispatchLog.Status.QUEUED,
    )
    MessageDispatchBatch.objects.filter(pk=batch.pk).update(
        total_count=F("total_count") + 1,
        queued_count=F("queued_count") + 1,
    )
    batch.refresh_from_db(fields=["total_count", "queued_count"])
    return log


def record_queue_failure(
    *,
    batch: MessageDispatchBatch,
    client_message_id: UUID,
    customer_id: int | None,
    phone: str,
    message: str,
    error: str,
) -> MessageDispatchLog:
    log = MessageDispatchLog.objects.create(
        batch=batch,
        client_message_id=client_message_id,
        customer_id=customer_id,
        phone=phone,
        message=message,
        status=MessageDispatchLog.Status.FAILED,
        error=error,
    )
    MessageDispatchBatch.objects.filter(pk=batch.pk).update(
        total_count=F("total_count") + 1,
        failed_count=F("failed_count") + 1,
        status=MessageDispatchBatch.Status.PROCESSING,
    )
    batch.refresh_from_db(fields=["total_count", "failed_count", "status"])
    return log


def finalize_batch_after_queue(batch: MessageDispatchBatch) -> MessageDispatchBatch:
    _refresh_batch_status(batch)
    return batch


@transaction.atomic
def apply_dispatch_status_update(
    *,
    client_message_id: str | UUID,
    status: str,
    error: str | None = None,
    batch_id: int | None = None,
) -> tuple[MessageDispatchLog, MessageDispatchBatch]:
    normalized_status = str(status or "").strip().lower()
    if normalized_status in {MessageDispatchLog.Status.QUEUED, MessageDispatchLog.Status.CANCELLED}:
        raise ValueError(f"Status '{normalized_status}' é interno do hunter e não pode ser enviado pelo worker.")
    if normalized_status not in MessageDispatchLog.WORKER_REPORTABLE_STATUSES:
        raise ValueError(f"Status inválido: {status}. Aceitos: processing, sent, failed.")

    queryset = MessageDispatchLog.objects.select_for_update().select_related("batch")
    if batch_id is not None:
        queryset = queryset.filter(batch_id=batch_id)

    log = queryset.get(client_message_id=client_message_id)
    previous = log.status
    if previous == MessageDispatchLog.Status.CANCELLED:
        return log, log.batch
    if previous == normalized_status and (not error or log.error == error):
        return log, log.batch

    log.status = normalized_status
    log.error = str(error or "")
    log.save(update_fields=["status", "error", "atualizado_em"])

    batch = MessageDispatchBatch.objects.select_for_update().get(pk=log.batch_id)
    counters: dict[str, Any] = {}
    if previous != normalized_status:
        counters[_count_field_for_status(previous)] = F(_count_field_for_status(previous)) - 1
        counters[_count_field_for_status(normalized_status)] = F(_count_field_for_status(normalized_status)) + 1

    if counters:
        MessageDispatchBatch.objects.filter(pk=batch.pk).update(**counters)
        batch.refresh_from_db()

    _refresh_batch_status(batch)
    return log, batch


@transaction.atomic
def cancel_in_flight_dispatch_logs(*, workshop_id: int) -> int:
    """Mark queued/processing logs as cancelled for a workshop and refresh batch counters."""
    logs = list(
        MessageDispatchLog.objects.select_for_update()
        .filter(
            batch__workshop_id=workshop_id,
            status__in=sorted(MessageDispatchLog.IN_FLIGHT_STATUSES),
        )
        .only("pk", "batch_id", "status")
    )
    if not logs:
        return 0

    by_batch_previous: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    log_ids: list[int] = []
    for log in logs:
        by_batch_previous[log.batch_id][log.status] += 1
        log_ids.append(log.pk)

    MessageDispatchLog.objects.filter(pk__in=log_ids).update(
        status=MessageDispatchLog.Status.CANCELLED,
        error="",
        atualizado_em=timezone.now(),
    )

    for batch_id, previous_counts in by_batch_previous.items():
        cancelled_delta = sum(previous_counts.values())
        updates: dict[str, Any] = {
            "cancelled_count": F("cancelled_count") + cancelled_delta,
        }
        for previous_status, count in previous_counts.items():
            field = _count_field_for_status(previous_status)
            updates[field] = F(field) - count
        MessageDispatchBatch.objects.filter(pk=batch_id).update(**updates)
        batch = MessageDispatchBatch.objects.select_for_update().get(pk=batch_id)
        _refresh_batch_status(batch)

    return len(log_ids)


def _count_field_for_status(status: str) -> str:
    mapping = {
        MessageDispatchLog.Status.QUEUED: "queued_count",
        MessageDispatchLog.Status.PROCESSING: "processing_count",
        MessageDispatchLog.Status.SENT: "sent_count",
        MessageDispatchLog.Status.FAILED: "failed_count",
        MessageDispatchLog.Status.CANCELLED: "cancelled_count",
    }
    return mapping[status]


def _refresh_batch_status(batch: MessageDispatchBatch) -> None:
    batch.refresh_from_db()
    if batch.total_count == 0:
        batch.status = MessageDispatchBatch.Status.FAILED
        batch.save(update_fields=["status", "atualizado_em"])
        return

    in_flight = batch.queued_count + batch.processing_count
    finished = batch.sent_count + batch.failed_count + batch.cancelled_count

    if in_flight > 0:
        batch.status = MessageDispatchBatch.Status.PROCESSING
    elif finished >= batch.total_count:
        if batch.cancelled_count > 0:
            batch.status = MessageDispatchBatch.Status.CANCELLED
        elif batch.failed_count == batch.total_count:
            batch.status = MessageDispatchBatch.Status.FAILED
        else:
            batch.status = MessageDispatchBatch.Status.COMPLETED
    elif batch.cancelled_count > 0:
        batch.status = MessageDispatchBatch.Status.CANCELLED
    elif batch.sent_count > 0 or batch.failed_count > 0:
        batch.status = MessageDispatchBatch.Status.PROCESSING
    else:
        batch.status = MessageDispatchBatch.Status.QUEUED
    batch.save(update_fields=["status", "atualizado_em"])
