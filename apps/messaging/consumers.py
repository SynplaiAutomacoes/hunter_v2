from __future__ import annotations

import logging
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.messaging.models import MessageDispatchBatch

logger = logging.getLogger(__name__)


class MessageDispatchBatchConsumer(AsyncJsonWebsocketConsumer):
    batch_id: int
    group_name: str

    async def connect(self) -> None:
        user = self.scope.get("user")
        if user is None or not getattr(user, "is_authenticated", False):
            await self.close(code=4401)
            return

        self.batch_id = int(self.scope["url_route"]["kwargs"]["batch_id"])
        allowed = await self._user_can_access_batch(user=user, batch_id=self.batch_id)
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

    @database_sync_to_async
    def _user_can_access_batch(self, *, user: Any, batch_id: int) -> bool:
        from apps.collaborators.models import WorkshopMember

        try:
            batch = MessageDispatchBatch.objects.get(pk=batch_id)
        except MessageDispatchBatch.DoesNotExist:
            return False

        if getattr(user, "is_superuser", False):
            return True

        return WorkshopMember.objects.filter(user=user, workshop_id=batch.workshop_id).exists()

    @database_sync_to_async
    def _batch_snapshot(self, batch_id: int) -> dict[str, Any]:
        batch = MessageDispatchBatch.objects.prefetch_related("logs").get(pk=batch_id)
        return {
            "id": batch.pk,
            "status": batch.status,
            "total_count": batch.total_count,
            "queued_count": batch.queued_count,
            "pending_count": batch.pending_count,
            "sent_count": batch.sent_count,
            "failed_count": batch.failed_count,
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
