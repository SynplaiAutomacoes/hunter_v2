from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from django.db import transaction
from django.db.models import F

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
    batch.refresh_from_db()
    if batch.total_count == 0:
        batch.status = MessageDispatchBatch.Status.FAILED
    elif batch.failed_count == batch.total_count:
        batch.status = MessageDispatchBatch.Status.FAILED
    elif batch.queued_count + batch.pending_count + batch.sent_count + batch.failed_count == batch.total_count:
        if batch.sent_count + batch.failed_count == batch.total_count:
            batch.status = MessageDispatchBatch.Status.COMPLETED
        else:
            batch.status = MessageDispatchBatch.Status.PROCESSING
    else:
        batch.status = MessageDispatchBatch.Status.PROCESSING
    batch.save(update_fields=["status", "atualizado_em"])
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
    allowed = {choice.value for choice in MessageDispatchLog.Status}
    if normalized_status not in allowed:
        raise ValueError(f"Status inválido: {status}")

    queryset = MessageDispatchLog.objects.select_for_update().select_related("batch")
    if batch_id is not None:
        queryset = queryset.filter(batch_id=batch_id)

    log = queryset.get(client_message_id=client_message_id)
    previous = log.status
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


def _count_field_for_status(status: str) -> str:
    mapping = {
        MessageDispatchLog.Status.QUEUED: "queued_count",
        MessageDispatchLog.Status.PENDING: "pending_count",
        MessageDispatchLog.Status.SENT: "sent_count",
        MessageDispatchLog.Status.FAILED: "failed_count",
    }
    return mapping[status]


def _refresh_batch_status(batch: MessageDispatchBatch) -> None:
    batch.refresh_from_db()
    finished = batch.sent_count + batch.failed_count
    if batch.total_count > 0 and finished >= batch.total_count:
        batch.status = MessageDispatchBatch.Status.COMPLETED
    elif batch.failed_count == batch.total_count and batch.total_count > 0:
        batch.status = MessageDispatchBatch.Status.FAILED
    elif batch.pending_count > 0 or batch.sent_count > 0 or batch.failed_count > 0:
        batch.status = MessageDispatchBatch.Status.PROCESSING
    else:
        batch.status = MessageDispatchBatch.Status.QUEUED
    batch.save(update_fields=["status", "atualizado_em"])
