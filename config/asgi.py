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

from apps.messaging.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(websocket_urlpatterns),
    }
)
