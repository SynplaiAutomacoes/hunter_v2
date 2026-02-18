from __future__ import annotations

import json
import logging

from django.db import transaction
from django.http import JsonResponse
from django.utils.crypto import constant_time_compare
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.finance.models import NfseBatch, NfseItem
from apps.finance.services.emission import build_webmania_webhook_token
from apps.finance.services.mappers import extract_items_from_batch, map_batch_payload, map_item_payload


logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):
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

    def post(self, request):
        if not self._is_authorized_request(request):
            logger.warning("Webhook de NFS-e rejeitado por token invalido")
            return JsonResponse({"ok": False, "message": "Unauthorized webhook request"}, status=403)

        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            logger.warning("Erro ao decodificar payload JSON no webhook de NFS-e")
            return JsonResponse({"ok": False, "message": "Invalid JSON"}, status=400)

        model = payload.get("modelo")
        if not model:
            logger.warning("Payload recebido sem campo 'modelo' no webhook de NFS-e")
            return JsonResponse({"ok": False, "message": "Missing 'modelo' field"}, status=400)

        if model == "lote_rps":
            batch_payload = map_batch_payload(payload)
            batch_uuid = batch_payload.get("uuid")
            if not batch_uuid:
                return JsonResponse({"ok": False, "message": "Missing batch uuid"}, status=400)

            batch = NfseBatch.objects.filter(uuid=batch_uuid).select_related("request", "workorder", "workshop").order_by("-id").first()
            if batch is None:
                return JsonResponse({"ok": False, "message": f"Batch não encontrado para UUID: {batch_uuid}"}, status=404)

            items = extract_items_from_batch(payload)

            with transaction.atomic():
                for key, value in batch_payload.items():
                    setattr(batch, key, value)
                batch.raw_payload = payload
                batch.save()

                for item_payload in items:
                    item_uuid = item_payload.get("uuid")
                    if not item_uuid:
                        continue

                    item, created = NfseItem.objects.get_or_create(
                        workorder=batch.workorder,
                        uuid=item_uuid,
                        defaults={
                            "workshop": batch.workshop,
                            "request": batch.request,
                            "batch": batch,
                            **item_payload,
                        },
                    )
                    if not created:
                        for key, value in item_payload.items():
                            setattr(item, key, value)
                        item.batch = batch
                        item.request = batch.request
                        item.raw_payload = payload
                        item.save()
                    else:
                        item.raw_payload = payload
                        item.save(update_fields=["raw_payload"])

                if batch.request:
                    batch.request.update_status_based_on_request(payload.get("status"))

            return JsonResponse({"ok": True, "message": "Payload processed successfully"}, status=200)

        if model == "nfse":
            item_payload = map_item_payload(payload)
            item_uuid = item_payload.get("uuid")
            if not item_uuid:
                return JsonResponse({"ok": False, "message": "Missing item uuid"}, status=400)

            item = NfseItem.objects.filter(uuid=item_uuid).select_related("request").order_by("-id").first()
            if item is None:
                return JsonResponse({"ok": False, "message": f"Item não encontrado para UUID: {item_uuid}"}, status=404)

            with transaction.atomic():
                for key, value in item_payload.items():
                    setattr(item, key, value)
                item.raw_payload = payload
                item.save()

            if item.request:
                item.request.update_status_based_on_request(payload.get("status"))

            return JsonResponse({"ok": True, "message": "Payload processed successfully"}, status=200)

        return JsonResponse({"ok": False, "message": "Invalid payload"}, status=400)
