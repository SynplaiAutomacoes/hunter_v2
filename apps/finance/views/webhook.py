from __future__ import annotations

import json
import logging
from typing import Any

from django.http import JsonResponse
from django.utils.crypto import constant_time_compare
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.core.infrastructure.providers import get_fiscal_service
from apps.core.domain.contracts.fiscal import FiscalServiceError
from apps.core.infrastructure.services.webmania.emission import build_webmania_webhook_token
from apps.core.infrastructure.services.webmania.webmania_webhooks import extract_event_uuid, process_webhook_event, store_webhook_event


logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):
    supported_models = {"lote_rps", "nfse", "nfe"}

    def get(self, request):
        return JsonResponse({"ok": True, "message": "Pong"}, status=200)

    @staticmethod
    def _request_webhook_token(request) -> str:
        header_token = request.headers.get("X-Webhook-Token", "")
        return str(request.GET.get("token") or header_token or "").strip()

    def _is_authorized_request(self, request) -> bool:
        expected_token = build_webmania_webhook_token()
        provided_token = self._request_webhook_token(request)
        return bool(provided_token) and constant_time_compare(provided_token, expected_token)

    @staticmethod
    def _deserialize_form_value(value: Any) -> Any:
        if not isinstance(value, str):
            return value

        normalized = value.strip()
        if not normalized:
            return value

        if normalized[0] not in "[{":
            return value

        try:
            return json.loads(normalized)
        except json.JSONDecodeError:
            return value

    def _parse_payload(self, request) -> dict[str, Any]:
        try:
            parsed_json = json.loads(request.body)
        except json.JSONDecodeError as exc:
            if not request.POST:
                raise exc

            payload = {key: self._deserialize_form_value(request.POST.get(key)) for key in request.POST.keys()}
            return payload

        if not isinstance(parsed_json, dict):
            raise json.JSONDecodeError("JSON root must be an object", str(request.body), 0)
        return parsed_json

    def post(self, request):
        if not self._is_authorized_request(request):
            logger.warning("Webhook da Webmania rejeitado por token invalido")
            return JsonResponse({"ok": False, "message": "Unauthorized webhook request"}, status=403)

        try:
            payload = self._parse_payload(request)
        except json.JSONDecodeError:
            logger.warning("Payload invalido recebido no webhook da Webmania")
            return JsonResponse({"ok": False, "message": "Invalid payload"}, status=400)

        model = str(payload.get("modelo") or "").strip().lower()
        if model not in self.supported_models:
            logger.warning("Payload recebido com modelo invalido no webhook da Webmania", extra={"modelo": model})
            return JsonResponse({"ok": False, "message": "Missing or invalid 'modelo' field"}, status=400)

        event_uuid = extract_event_uuid(payload)
        if not event_uuid:
            return JsonResponse({"ok": False, "message": "Missing event uuid"}, status=400)

        logger.info("webmania_webhook_received model=%s uuid=%s", model, event_uuid)

        event = store_webhook_event(payload=payload)
        if process_webhook_event(event):
            return JsonResponse({"ok": True, "message": "Payload processed successfully"}, status=200)

        return JsonResponse(
            {"ok": True, "message": "Payload accepted for deferred processing", "event_id": event.pk},
            status=202,
        )
