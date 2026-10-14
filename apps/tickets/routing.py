from __future__ import annotations

from django.urls import path

from apps.tickets.consumers import TicketChatConsumer

websocket_urlpatterns = [
    path("ws/tickets/<int:ticket_id>/chat/", TicketChatConsumer.as_asgi()),
]
