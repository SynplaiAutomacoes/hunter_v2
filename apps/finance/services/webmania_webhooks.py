from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.finance.models.finance import NfeItem, NfseBatch, NfseItem, WebmaniaWebhookEvent
from apps.finance.services.emission import apply_nfse_batch_payload, apply_nfse_item_payload
from apps.finance.services.mappers import extract_items_from_batch
from apps.finance.services.nfe_emission import apply_nfe_item_payload


def extract_event_uuid(payload: dict[str, Any]) -> str:
    return str(payload.get("uuid") or "").strip()


def store_webhook_event(*, payload: dict[str, Any]) -> WebmaniaWebhookEvent:
    return WebmaniaWebhookEvent.objects.create(
        model=str(payload.get("modelo") or "").strip().lower(),
        event_uuid=extract_event_uuid(payload),
        payload=payload,
    )


def _mark_event_processed(event: WebmaniaWebhookEvent) -> None:
    event.processed_at = timezone.now()
    event.processing_error = ""
    event.save(update_fields=["processed_at", "processing_error", "atualizado_em"])


def _mark_event_deferred(event: WebmaniaWebhookEvent, *, error: str) -> None:
    event.processing_error = error
    event.save(update_fields=["processing_error", "atualizado_em"])


def process_webhook_event(event: WebmaniaWebhookEvent) -> bool:
    payload = dict(event.payload or {})
    model = str(event.model or "").strip().lower()
    event_uuid = str(event.event_uuid or "").strip()
    webhook_received_at = timezone.now()

    if model == "lote_rps":
        batch = NfseBatch.objects.filter(uuid=event_uuid).select_related("request").order_by("-id").first()
        if batch is None:
            _mark_event_deferred(event, error=f"Lote {event_uuid} ainda nao foi sincronizado localmente.")
            return False

        with transaction.atomic():
            batch = apply_nfse_batch_payload(
                batch=batch,
                response_payload=payload,
                webhook_received_at=webhook_received_at,
            )
            for item_payload in extract_items_from_batch(payload):
                item_uuid = str(item_payload.get("uuid") or "").strip()
                if not item_uuid:
                    continue

                item, _ = NfseItem.objects.get_or_create(
                    workorder=batch.workorder,
                    uuid=item_uuid,
                    defaults={
                        "workshop": batch.workshop,
                        "request": batch.request,
                        "batch": batch,
                    },
                )
                item.batch = batch
                item.request = batch.request
                apply_nfse_item_payload(
                    item=item,
                    response_payload=item_payload,
                    webhook_received_at=webhook_received_at,
                )

        _mark_event_processed(event)
        return True

    if model == "nfse":
        nfse_item = NfseItem.objects.filter(uuid=event_uuid).select_related("request").order_by("-id").first()
        if nfse_item is None:
            _mark_event_deferred(event, error=f"NFS-e {event_uuid} ainda nao foi sincronizada localmente.")
            return False

        with transaction.atomic():
            apply_nfse_item_payload(
                item=nfse_item,
                response_payload=payload,
                webhook_received_at=webhook_received_at,
            )

        _mark_event_processed(event)
        return True

    if model == "nfe":
        nfe_item = NfeItem.objects.filter(uuid=event_uuid).select_related("request").order_by("-id").first()
        if nfe_item is None:
            _mark_event_deferred(event, error=f"NF-e {event_uuid} ainda nao foi sincronizada localmente.")
            return False

        with transaction.atomic():
            apply_nfe_item_payload(
                item=nfe_item,
                response_payload=payload,
                webhook_received_at=webhook_received_at,
            )

        _mark_event_processed(event)
        return True

    _mark_event_deferred(event, error=f"Modelo de webhook nao suportado: {model or '-'}")
    return False


def process_pending_webhook_events(*, model: str | None = None, event_uuid: str | None = None, limit: int | None = None) -> int:
    queryset = WebmaniaWebhookEvent.objects.filter(processed_at__isnull=True).order_by("criado_em", "pk")
    if model:
        queryset = queryset.filter(model=str(model).strip().lower())
    if event_uuid:
        queryset = queryset.filter(event_uuid=str(event_uuid).strip())
    if limit is not None:
        queryset = queryset[:limit]

    processed = 0
    for event in queryset:
        if process_webhook_event(event):
            processed += 1
    return processed
