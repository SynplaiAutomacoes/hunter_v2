from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.finance.models.finance import FiscalDocumentEvent, NfeItem, NfseBatch, NfseItem, WebmaniaWebhookEvent
from apps.finance.services.emission import apply_nfse_batch_payload, apply_nfse_item_payload
from apps.finance.services.mappers import extract_items_from_batch
from apps.finance.services.nfe_events import apply_cce_event_payload
from apps.finance.services.nfe_emission import apply_nfe_item_payload
from apps.finance.services.nfe_adjustment import apply_nfe_adjustment_document_payload, is_ambiguous_nfe_adjustment_webhook, resolve_nfe_adjustment_document_for_webhook
from apps.finance.services.nfe_complementary import apply_nfe_complementary_document_payload, is_ambiguous_nfe_complementary_webhook, resolve_nfe_complementary_document_for_webhook
from apps.finance.services.nfe_returns import apply_nfe_return_document_payload, is_ambiguous_nfe_return_webhook, resolve_nfe_return_document_for_webhook
from apps.finance.services.nfce_emission import apply_nfce_document_payload, is_ambiguous_nfce_webhook, resolve_nfce_document_for_webhook


def _unique_or_none(queryset: Any) -> Any | None:
    matches = list(queryset.order_by("-id")[:2])
    if len(matches) != 1:
        return None
    return matches[0]


def extract_event_uuid(payload: dict[str, Any]) -> str:
    return str(payload.get("uuid") or "").strip()


def build_webhook_fingerprint(*, payload: dict[str, Any]) -> str:
    model = str(payload.get("modelo") or "").strip().lower()
    event_uuid = extract_event_uuid(payload)
    canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{model}:{event_uuid}:{canonical_payload}".encode("utf-8")).hexdigest()


def store_webhook_event(*, payload: dict[str, Any]) -> WebmaniaWebhookEvent:
    fingerprint = build_webhook_fingerprint(payload=payload)
    event, _ = WebmaniaWebhookEvent.objects.get_or_create(
        fingerprint=fingerprint,
        defaults={
            "model": str(payload.get("modelo") or "").strip().lower(),
            "event_uuid": extract_event_uuid(payload),
            "payload": payload,
        },
    )
    return event


def _status_rank(model: str, status: str) -> int:
    normalized = str(status or "").strip().lower()
    if model == "lote_rps":
        return {
            "processando": 10,
            "contingencia": 20,
            "agendado": 25,
            "processado": 30,
            "reprovado": 40,
            "cancelado": 50,
        }.get(normalized, 0)
    if model == "nfse":
        return {
            "processando": 10,
            "contingencia": 20,
            "agendado": 25,
            "aprovado": 30,
            "reprovado": 40,
            "cancelado": 50,
        }.get(normalized, 0)
    if model == "nfe":
        return {
            "processando": 10,
            "contingencia": 20,
            "aprovado": 30,
            "reprovado": 40,
            "denegado": 40,
            "cancelado": 50,
        }.get(normalized, 0)
    if model == "cce":
        return {
            "started": 5,
            "sent": 8,
            "processando": 10,
            "uncertain": 15,
            "aprovado": 30,
            "reprovado": 40,
            "failed": 40,
        }.get(normalized, 0)
    return 0


def _is_regressive_status(*, model: str, current_status: str, incoming_status: str) -> bool:
    incoming_rank = _status_rank(model, incoming_status)
    current_rank = _status_rank(model, current_status)
    return bool(incoming_rank and current_rank and incoming_rank < current_rank)


def _mark_event_processed(event: WebmaniaWebhookEvent) -> None:
    event.processed_at = timezone.now()
    event.processing_error = ""
    event.save(update_fields=["processed_at", "processing_error", "atualizado_em"])


def _mark_event_deferred(event: WebmaniaWebhookEvent, *, error: str) -> None:
    event.processing_error = error
    event.save(update_fields=["processing_error", "atualizado_em"])


def process_webhook_event(event: WebmaniaWebhookEvent) -> bool:
    if event.processed_at is not None:
        return True

    payload = dict(event.payload or {})
    model = str(event.model or "").strip().lower()
    event_uuid = str(event.event_uuid or "").strip()
    webhook_received_at = timezone.now()

    if model == "lote_rps":
        batch = _unique_or_none(NfseBatch.objects.filter(uuid=event_uuid).select_related("request"))
        if batch is None:
            _mark_event_deferred(event, error=f"Lote {event_uuid} ainda nao foi sincronizado localmente ou esta ambiguo entre oficinas.")
            return False

        with transaction.atomic():
            if not _is_regressive_status(model="lote_rps", current_status=batch.status, incoming_status=str(payload.get("status") or "")):
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
                    if not _is_regressive_status(model="nfse", current_status=item.status, incoming_status=str(item_payload.get("status") or "")):
                        apply_nfse_item_payload(
                            item=item,
                            response_payload=item_payload,
                            webhook_received_at=webhook_received_at,
                        )

        _mark_event_processed(event)
        return True

    if model == "nfse":
        nfse_item = _unique_or_none(NfseItem.objects.filter(uuid=event_uuid).select_related("request"))
        if nfse_item is None:
            _mark_event_deferred(event, error=f"Nota Fiscal de Serviço {event_uuid} ainda nao foi sincronizada localmente ou esta ambigua entre oficinas.")
            return False

        with transaction.atomic():
            if not _is_regressive_status(model="nfse", current_status=nfse_item.status, incoming_status=str(payload.get("status") or "")):
                apply_nfse_item_payload(
                    item=nfse_item,
                    response_payload=payload,
                    webhook_received_at=webhook_received_at,
                )

        _mark_event_processed(event)
        return True

    if model == "nfce":
        nfce_document = resolve_nfce_document_for_webhook(payload=payload)
        if nfce_document is not None:
            with transaction.atomic():
                nfce_document = nfce_document.__class__.objects.select_for_update().get(pk=nfce_document.pk)
                if not _is_regressive_status(model="nfe", current_status=nfce_document.status, incoming_status=str(payload.get("status") or "")):
                    apply_nfce_document_payload(document=nfce_document, response_payload=payload)

            _mark_event_processed(event)
            return True
        if is_ambiguous_nfce_webhook(payload=payload):
            _mark_event_deferred(event, error=f"NFC-e {event_uuid or str(payload.get('chave') or '').strip()} ambigua entre documentos.")
            return False
        _mark_event_deferred(event, error=f"NFC-e {event_uuid} ainda nao foi sincronizada localmente ou esta ambigua entre oficinas.")
        return False

    if model == "nfe":
        adjustment_document = resolve_nfe_adjustment_document_for_webhook(payload=payload)
        if adjustment_document is not None:
            with transaction.atomic():
                adjustment_document = adjustment_document.__class__.objects.select_for_update().get(pk=adjustment_document.pk)
                if not _is_regressive_status(model="nfe", current_status=adjustment_document.status, incoming_status=str(payload.get("status") or "")):
                    apply_nfe_adjustment_document_payload(document=adjustment_document, response_payload=payload)

            _mark_event_processed(event)
            return True
        if is_ambiguous_nfe_adjustment_webhook(payload=payload):
            _mark_event_deferred(event, error=f"Nota Fiscal de Ajuste {event_uuid or str(payload.get('chave') or '').strip()} ambigua entre documentos.")
            return False

        complementary_document = resolve_nfe_complementary_document_for_webhook(payload=payload)
        if complementary_document is not None:
            with transaction.atomic():
                complementary_document = complementary_document.__class__.objects.select_for_update().get(pk=complementary_document.pk)
                if not _is_regressive_status(model="nfe", current_status=complementary_document.status, incoming_status=str(payload.get("status") or "")):
                    apply_nfe_complementary_document_payload(document=complementary_document, response_payload=payload)

            _mark_event_processed(event)
            return True
        if is_ambiguous_nfe_complementary_webhook(payload=payload):
            _mark_event_deferred(event, error=f"Nota Fiscal Complementar {event_uuid or str(payload.get('chave') or '').strip()} ambigua entre documentos derivados.")
            return False

        derived_document = resolve_nfe_return_document_for_webhook(payload=payload)
        if derived_document is not None:
            with transaction.atomic():
                derived_document = derived_document.__class__.objects.select_for_update().get(pk=derived_document.pk)
                if not _is_regressive_status(model="nfe", current_status=derived_document.status, incoming_status=str(payload.get("status") or "")):
                    apply_nfe_return_document_payload(document=derived_document, response_payload=payload)

            _mark_event_processed(event)
            return True
        if is_ambiguous_nfe_return_webhook(payload=payload):
            _mark_event_deferred(event, error=f"Devolucao/estorno NF-e {event_uuid or str(payload.get('chave') or '').strip()} ambiguo entre documentos derivados.")
            return False

        nfe_item = _unique_or_none(NfeItem.objects.filter(uuid=event_uuid).select_related("request"))
        if nfe_item is None:
            _mark_event_deferred(event, error=f"Nota Fiscal {event_uuid} ainda nao foi sincronizada localmente ou esta ambigua entre oficinas.")
            return False

        with transaction.atomic():
            if not _is_regressive_status(model="nfe", current_status=nfe_item.status, incoming_status=str(payload.get("status") or "")):
                apply_nfe_item_payload(
                    item=nfe_item,
                    response_payload=payload,
                    webhook_received_at=webhook_received_at,
                )

        _mark_event_processed(event)
        return True

    if model == "cce":
        cce_event = _unique_or_none(FiscalDocumentEvent.objects.filter(remote_uuid=event_uuid).select_related("document", "document__legacy_nfe_item"))
        if cce_event is None:
            cce_event = _unique_or_none(
                FiscalDocumentEvent.objects.filter(emission_attempts__remote_uuid=event_uuid).select_related("document", "document__legacy_nfe_item")
            )
        if cce_event is None:
            access_key = str(payload.get("chave") or "").strip()
            event_sequence = payload.get("evento")
            if access_key and str(event_sequence or "").isdigit():
                cce_event = _unique_or_none(
                    FiscalDocumentEvent.objects.filter(document__access_key=access_key, event_type="cce", event_sequence=int(event_sequence)).select_related("document", "document__legacy_nfe_item")
                )
        if cce_event is None:
            _mark_event_deferred(event, error=f"Carta de correcao {event_uuid} ainda nao foi sincronizada localmente ou esta ambigua.")
            return False

        with transaction.atomic():
            cce_event = FiscalDocumentEvent.objects.select_for_update().get(pk=cce_event.pk)
            if not _is_regressive_status(model="cce", current_status=cce_event.status, incoming_status=str(payload.get("status") or "")):
                apply_cce_event_payload(event=cce_event, response_payload=payload)

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
