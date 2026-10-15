from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs

from channels.db import database_sync_to_async  # type: ignore[import-untyped]
from channels.generic.websocket import AsyncJsonWebsocketConsumer  # type: ignore[import-untyped]

from apps.tickets.application.services.chat import serialize_message, ticket_chat_group_name
from apps.tickets.application.services.ws_auth import (
    TicketChatWebSocketAuthError,
    token_can_access_ticket_chat,
    verify_ticket_chat_ws_token,
)
from apps.tickets.models import TicketMessage

logger = logging.getLogger(__name__)


class TicketChatConsumer(AsyncJsonWebsocketConsumer):  # type: ignore[misc,no-any-unimported]
    ticket_id: int
    group_name: str

    async def connect(self) -> None:
        self.ticket_id = int(self.scope["url_route"]["kwargs"]["ticket_id"])
        token = self._extract_token()
        try:
            user_id, token_ticket_id = verify_ticket_chat_ws_token(token)
        except TicketChatWebSocketAuthError:
            await self.close(code=4401)
            return

        if token_ticket_id != self.ticket_id:
            await self.close(code=4403)
            return

        allowed = await database_sync_to_async(token_can_access_ticket_chat)(
            user_id=user_id,
            ticket_id=self.ticket_id,
        )
        if not allowed:
            await self.close(code=4403)
            return

        self.group_name = ticket_chat_group_name(self.ticket_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        messages = await self._recent_messages(self.ticket_id)
        await self.send_json({"type": "chat.snapshot", "messages": messages})

    async def disconnect(self, code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def chat_message(self, event: dict[str, Any]) -> None:
        await self.send_json({"type": "chat.message", **event.get("payload", {})})

    def _extract_token(self) -> str:
        query_string = self.scope.get("query_string", b"")
        if isinstance(query_string, bytes):
            query_string = query_string.decode("utf-8", errors="ignore")
        params = parse_qs(query_string)
        values = params.get("token") or []
        return str(values[0]) if values else ""

    @database_sync_to_async
    def _recent_messages(self, ticket_id: int) -> list[dict[str, Any]]:
        qs = TicketMessage.objects.filter(ticket_id=ticket_id).select_related("author").order_by("created_at")[:200]
        return [serialize_message(message) for message in qs]
