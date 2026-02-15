import json

from django.db import transaction
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView

from apps.finance.models import NfseBatch, NfseItem, NfseRequest
from apps.finance.services.mappers import map_batch_payload, map_item_payload, extract_items_from_batch


@method_decorator(csrf_exempt, name="dispatch")
class WebhookView(View):
    def get(self, request):
        return JsonResponse({"ok": True, "message": "Pong"}, status=200)

    def post(self, request):
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            print(f"Erro ao decodificar JSON: {request.body}")
            return JsonResponse({"ok": False, "message": "Invalid JSON"}, status=400)

        model = payload.get("modelo")

        if not model:
            print(f"Payload recebido sem campo 'modelo': {payload}")
            return JsonResponse({"ok": False, "message": "Missing 'modelo' field"}, status=400)

        if model == "lote_rps":
            batch_payload = map_batch_payload(payload)

            try:
                batch = NfseBatch.objects.get(uuid=batch_payload.get("uuid"))
            except NfseBatch.DoesNotExist:
                return JsonResponse({"ok": False, "message": f"Batch não encontrado para UUID: {batch_payload.get('uuid')}"}, status=404)

            items = extract_items_from_batch(payload)

            with transaction.atomic():
                for key, value in batch_payload.items():
                    setattr(batch, key, value)
                batch.save()

                for item_payload in items:
                    item, created = NfseItem.objects.get_or_create(
                        workorder=batch.workorder,
                        uuid=item_payload.get("uuid"),
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
                        item.save()

                batch.request.update_status_based_on_request(payload.get("status"))

            return JsonResponse({"ok": True, "message": "Payload processed successfully"}, status=200)

        elif model == "nfse":
            item_payload = map_item_payload(payload)

            try:
                item = NfseItem.objects.get(uuid=item_payload.get("uuid"))
            except NfseItem.DoesNotExist:
                return JsonResponse({"ok": False, "message": f"Item não encontrado para UUID: {item_payload.get('uuid')}"}, status=404)

            with transaction.atomic():
                for key, value in item_payload.items():
                    setattr(item, key, value)
                item.save()

            item.request.update_status_based_on_request(payload.get("status"))

            return JsonResponse({"ok": True, "message": "Payload processed successfully"}, status=200)

        else:
            return JsonResponse({"ok": False, "message": "Invalid payload"}, status=400)



class CreateBatchView(CreateView):
    pass

