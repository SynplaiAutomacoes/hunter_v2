from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.messaging.application.services.dispatch_ws_auth import (
    DispatchWebSocketAuthError,
    token_can_access_dispatch_batch,
    verify_dispatch_ws_token,
)
from apps.messaging.models import MessageDispatchBatch

logger = logging.getLogger(__name__)


class MessageDispatchBatchConsumer(AsyncJsonWebsocketConsumer):
    batch_id: int
    group_name: str

    async def connect(self) -> None:
        self.batch_id = int(self.scope["url_route"]["kwargs"]["batch_id"])
        token = self._extract_token()
        try:
            user_id, workshop_id = verify_dispatch_ws_token(token)
        except DispatchWebSocketAuthError:
            await self.close(code=4401)
            return

        allowed = await database_sync_to_async(token_can_access_dispatch_batch)(
            user_id=user_id,
            workshop_id=workshop_id,
            batch_id=self.batch_id,
        )
        if not allowed:
            await self.close(code=4403)
            return

        self.group_name = f"dispatch.batch.{self.batch_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        snapshot = await self._batch_snapshot(self.batch_id)
        await self.send_json({"type": "batch.snapshot", "batch": snapshot})

    async def disconnect(self, code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def dispatch_status(self, event: dict[str, Any]) -> None:
        await self.send_json({"type": "dispatch.status", **event.get("payload", {})})

    def _extract_token(self) -> str:
        query_string = self.scope.get("query_string", b"")
        if isinstance(query_string, bytes):
            query_string = query_string.decode("utf-8", errors="ignore")
        params = parse_qs(query_string)
        values = params.get("token") or []
        return str(values[0]) if values else ""

    @database_sync_to_async
    def _batch_snapshot(self, batch_id: int) -> dict[str, Any]:
        batch = MessageDispatchBatch.objects.prefetch_related("logs").get(pk=batch_id)
        return {
            "id": batch.pk,
            "status": batch.status,
            "total_count": batch.total_count,
            "queued_count": batch.queued_count,
            "processing_count": batch.processing_count,
            "sent_count": batch.sent_count,
            "failed_count": batch.failed_count,
            "cancelled_count": batch.cancelled_count,
            "logs": [
                {
                    "client_message_id": str(log.client_message_id),
                    "customer_id": log.customer_id,
                    "phone": log.phone,
                    "status": log.status,
                    "error": log.error,
                }
                for log in batch.logs.all()
            ],
        }
