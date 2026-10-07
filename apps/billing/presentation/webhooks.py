from __future__ import annotations

import json
import logging

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.billing.domain.contracts import BillingServiceError
from apps.billing.infrastructure.providers import get_billing_service
from apps.billing.infrastructure.services.webhook_processor import (
    claim_webhook_event,
    mark_webhook_processed,
    process_stripe_event,
)

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        return JsonResponse({"ok": True, "service": "stripe"})

    def post(self, request: HttpRequest) -> HttpResponse:
        payload = request.body
        signature_header = str(request.headers.get("Stripe-Signature") or "")

        try:
            event = get_billing_service().construct_webhook_event(
                payload=payload,
                signature_header=signature_header,
            )
        except BillingServiceError as exc:
            logger.warning("Stripe webhook rejeitado: %s", exc)
            return JsonResponse({"ok": False, "message": str(exc)}, status=400)

        try:
            raw_payload = json.loads(payload.decode("utf-8")) if payload else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            raw_payload = {"event_id": event.event_id, "type": event.event_type}

        claimed = claim_webhook_event(
            event_id=event.event_id,
            event_type=event.event_type,
            payload=raw_payload if isinstance(raw_payload, dict) else {},
        )
        if claimed is None:
            return JsonResponse({"ok": True, "duplicate": True})

        try:
            process_stripe_event(event_type=event.event_type, data=event.data)
            mark_webhook_processed(claimed)
        except Exception:
            logger.exception("Erro ao processar evento Stripe %s", event.event_id)
            return JsonResponse({"ok": False, "message": "Processing error"}, status=500)

        return JsonResponse({"ok": True})
