from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer  # type: ignore[import-untyped]
from django.db import transaction

from apps.tickets.application.services.notifications import TicketNotificationService
from apps.tickets.models import Ticket, TicketMessage
from apps.tickets.permissions import can_view_ticket


class TicketChatError(Exception):
    pass


def ticket_chat_group_name(ticket_id: int) -> str:
    return f"ticket.chat.{int(ticket_id)}"


def serialize_message(message: TicketMessage) -> dict[str, Any]:
    return {
        "id": message.pk,
        "ticket_id": message.ticket_id,
        "author_id": message.author_id,
        "author_username": message.author.get_username() if message.author_id else "",
        "body": message.body,
        "created_at": message.created_at.isoformat() if message.created_at else "",
    }


def broadcast_ticket_message(message: TicketMessage) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        ticket_chat_group_name(message.ticket_id),
        {
            "type": "chat.message",
            "payload": serialize_message(message),
        },
    )


@transaction.atomic
def post_ticket_message(*, ticket: Ticket, author, body: str) -> TicketMessage:
    if not can_view_ticket(user=author, ticket=ticket):
        raise TicketChatError("Sem permissão para enviar mensagem neste chamado.")
    text = (body or "").strip()
    if not text:
        raise TicketChatError("Mensagem vazia.")
    if len(text) > 4000:
        raise TicketChatError("Mensagem muito longa.")

    message = TicketMessage.objects.create(ticket=ticket, author=author, body=text)
    TicketNotificationService.notify_chat_message(ticket=ticket, author=author, body=text)
    transaction.on_commit(lambda: broadcast_ticket_message(message))
    return message
