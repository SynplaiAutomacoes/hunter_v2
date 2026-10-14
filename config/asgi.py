"""
ASGI config for config project.

Used by the dedicated realtime service (Daphne/Uvicorn), not by Gunicorn WSGI.
WebSocket auth uses signed query tokens (not session cookies), so the realtime
service can live on a different Railway public domain than the web app.
"""

from __future__ import annotations

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

from apps.messaging.routing import websocket_urlpatterns as messaging_websocket_urlpatterns  # noqa: E402
from apps.tickets.routing import websocket_urlpatterns as tickets_websocket_urlpatterns  # noqa: E402

websocket_urlpatterns = [
    *messaging_websocket_urlpatterns,
    *tickets_websocket_urlpatterns,
]

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(websocket_urlpatterns),
    }
)
