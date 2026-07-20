from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.messaging.application.services.dispatch_history import apply_dispatch_status_update
from apps.messaging.models import MessageDispatchBatch, MessageDispatchLog

logger = logging.getLogger(__name__)


def ingest_dispatch_status(
    *,
    client_message_id: str | UUID,
    status: str,
    batch_id: int | None = None,
    error: str | None = None,
) -> tuple[MessageDispatchLog, MessageDispatchBatch]:
    log, batch = apply_dispatch_status_update(
        client_message_id=client_message_id,
        status=status,
        error=error,
        batch_id=batch_id,
    )
    _broadcast_status(log=log, batch=batch)
    return log, batch


def _broadcast_status(*, log: MessageDispatchLog, batch: MessageDispatchBatch) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning("dispatch_realtime_no_channel_layer", extra={"batch_id": batch.pk})
        return

    payload: dict[str, Any] = {
        "batch_id": batch.pk,
        "client_message_id": str(log.client_message_id),
        "status": log.status,
        "error": log.error,
        "batch_status": batch.status,
        "queued_count": batch.queued_count,
        "processing_count": batch.processing_count,
        "sent_count": batch.sent_count,
        "failed_count": batch.failed_count,
        "cancelled_count": batch.cancelled_count,
        "total_count": batch.total_count,
    }
    async_to_sync(channel_layer.group_send)(
        f"dispatch.batch.{batch.pk}",
        {"type": "dispatch.status", "payload": payload},
    )
