from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from apps.messaging.application.services.dispatch_realtime import ingest_dispatch_status
from apps.messaging.models import MessageDispatchLog

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class MessageDispatchStatusIngestView(View):
    """HTTP ingest used by the external worker to report per-message status."""

    http_method_names = ["post"]

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        if not self._is_authorized(request):
            return JsonResponse({"ok": False, "error": "unauthorized"}, status=401)

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

        client_message_id = payload.get("client_message_id")
        status = payload.get("status")
        if not client_message_id or not status:
            return JsonResponse({"ok": False, "error": "client_message_id and status are required"}, status=400)

        batch_id = payload.get("batch_id")
        try:
            log, batch = ingest_dispatch_status(
                client_message_id=client_message_id,
                status=str(status),
                batch_id=int(batch_id) if batch_id is not None else None,
                error=payload.get("error"),
            )
        except MessageDispatchLog.DoesNotExist:
            return JsonResponse({"ok": False, "error": "message_not_found"}, status=404)
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        except Exception:
            logger.exception("dispatch_status_ingest_failed", extra={"client_message_id": client_message_id})
            return JsonResponse({"ok": False, "error": "internal_error"}, status=500)

        return JsonResponse(
            {
                "ok": True,
                "client_message_id": str(log.client_message_id),
                "status": log.status,
                "batch_id": batch.pk,
                "batch_status": batch.status,
            }
        )

    @staticmethod
    def _is_authorized(request: HttpRequest) -> bool:
        expected = str(getattr(settings, "MESSAGE_DISPATCH_STATUS_TOKEN", "") or "").strip()
        if not expected:
            # Allow local/dev when token is not configured; require token in real envs.
            return True
        header = request.headers.get("X-Dispatch-Status-Token") or request.headers.get("Authorization") or ""
        if header.startswith("Bearer "):
            header = header[7:].strip()
        return header == expected
