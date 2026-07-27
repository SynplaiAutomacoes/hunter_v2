from __future__ import annotations

from django.urls import path

from apps.messaging.consumers import MessageDispatchBatchConsumer

websocket_urlpatterns = [
    path("ws/dispatch/<int:batch_id>/", MessageDispatchBatchConsumer.as_asgi()),
]
