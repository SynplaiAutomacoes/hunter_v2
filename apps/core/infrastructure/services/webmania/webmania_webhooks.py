from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.finance.models.finance import FiscalDocumentEvent, FiscalDocumentEventStatus, NfeItem, NfseBatch, NfseItem, WebmaniaWebhookEvent
from apps.core.infrastructure.services.webmania.emission import apply_nfse_batch_payload, apply_nfse_item_payload
from apps.finance.services.mappers import extract_items_from_batch
from apps.core.infrastructure.services.webmania.nfe_emission import apply_nfe_item_payload
from apps.finance.services.nfe_events import NfeCorrectionError, confirm_cce_event_from_payload, validate_cce_payload_identity
from apps.finance.services.nfe_returns import (
    NfeReturnError,
    confirm_nfe_return_document_from_payload,
    is_ambiguous_nfe_return_webhook,
    resolve_nfe_return_document_for_webhook,
    validate_nfe_return_document_link,
    validate_nfe_return_payload_identity,
)


def extract_event_uuid(payload: dict[str, Any]) -> str:
    return str(payload.get("uuid") or "").strip()


def store_webhook_event(*, payload: dict[str, Any]) -> WebmaniaWebhookEvent:
    model = str(payload.get("modelo") or "").strip().lower()
    event_uuid = extract_event_uuid(payload)
    if model == "cce" and event_uuid:
        duplicate = WebmaniaWebhookEvent.objects.filter(model=model, event_uuid=event_uuid, payload=payload).order_by("pk").first()
        if duplicate is not None:
            return duplicate

    return WebmaniaWebhookEvent.objects.create(
        model=model,
        event_uuid=event_uuid,
        payload=payload,
    )


def _mark_event_processed(event: WebmaniaWebhookEvent) -> None:
    event.processed_at = timezone.now()
    event.processing_error = ""
    event.save(update_fields=["processed_at", "processing_error", "atualizado_em"])


def _mark_event_deferred(event: WebmaniaWebhookEvent, *, error: str) -> None:
    event.processing_error = error
    event.save(update_fields=["processing_error", "atualizado_em"])


def _resolve_cce_event(*, payload: dict[str, Any], event_uuid: str) -> FiscalDocumentEvent | None:
    queryset = FiscalDocumentEvent.objects.select_related("document")
    if event_uuid:
        event = queryset.filter(remote_uuid=event_uuid).first()
        if event is not None:
            return event

    access_key = str(payload.get("chave") or "").strip()
    sequence = payload.get("evento")
    if not access_key or not str(sequence or "").isdigit():
        return None

    candidates = queryset.filter(
        document__access_key=access_key,
        event_sequence=int(sequence),
        status__in=[
            FiscalDocumentEventStatus.STARTED,
            FiscalDocumentEventStatus.SENT,
            FiscalDocumentEventStatus.PROCESSING,
            FiscalDocumentEventStatus.UNCERTAIN,
        ],
    )
    return candidates.first() if candidates.count() == 1 else None


def _is_regressive_cce_status(*, current_status: str, incoming_status: str) -> bool:
    ranks = {
        "started": 5,
        "sent": 8,
        "processando": 10,
        "uncertain": 15,
        "aprovado": 30,
        "succeeded": 30,
        "reprovado": 40,
        "failed": 40,
    }
    current_rank = ranks.get(str(current_status or "").strip().lower(), 0)
    incoming_rank = ranks.get(str(incoming_status or "").strip().lower(), 0)
    return bool(current_rank and incoming_rank and incoming_rank < current_rank)


def _is_regressive_nfe_status(*, current_status: str, incoming_status: str) -> bool:
    ranks = {
        "processando": 10,
        "uncertain": 15,
        "contingencia": 20,
        "aprovado": 30,
        "reprovado": 40,
        "denegado": 40,
        "cancelado": 50,
    }
    current_rank = ranks.get(str(current_status or "").strip().lower(), 0)
    incoming_rank = ranks.get(str(incoming_status or "").strip().lower(), 0)
    return bool(current_rank and incoming_rank and incoming_rank < current_rank)


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
            _mark_event_deferred(event, error=f"Nota Fiscal de Serviço {event_uuid} ainda nao foi sincronizada localmente.")
            return False

        with transaction.atomic():
            apply_nfse_item_payload(
                item=nfse_item,
                response_payload=payload,
                webhook_received_at=webhook_received_at,
            )

        _mark_event_processed(event)
        return True

    if model == "cce":
        cce_event = _resolve_cce_event(payload=payload, event_uuid=event_uuid)
        if cce_event is None:
            _mark_event_deferred(event, error=f"Carta de correcao {event_uuid or '-'} ainda nao foi sincronizada localmente ou esta ambigua.")
            return False

        try:
            with transaction.atomic():
                cce_event = FiscalDocumentEvent.objects.select_for_update().select_related("document").get(pk=cce_event.pk)
                validate_cce_payload_identity(
                    event=cce_event,
                    payload=payload,
                    expected_uuid=str(cce_event.remote_uuid or "").strip() or None,
                    require_sequence=True,
                    require_document_key=True,
                )
                if not _is_regressive_cce_status(current_status=cce_event.status, incoming_status=str(payload.get("status") or "")):
                    confirm_cce_event_from_payload(event=cce_event, response_payload=payload)
        except NfeCorrectionError as exc:
            _mark_event_deferred(event, error=str(exc))
            return False

        _mark_event_processed(event)
        return True

    if model == "nfe":
        derived_document = resolve_nfe_return_document_for_webhook(payload=payload)
        if derived_document is not None:
            try:
                with transaction.atomic():
                    derived_document = derived_document.__class__.objects.select_for_update().get(pk=derived_document.pk)
                    validate_nfe_return_document_link(document=derived_document)
                    validate_nfe_return_payload_identity(
                        document=derived_document,
                        payload=payload,
                        expected_uuid=str(derived_document.remote_uuid or "").strip(),
                        expected_access_key=str(derived_document.access_key or "").strip(),
                        require_model=True,
                        require_safe_identifier=True,
                    )
                    if not _is_regressive_nfe_status(current_status=derived_document.status, incoming_status=str(payload.get("status") or "")):
                        confirm_nfe_return_document_from_payload(document=derived_document, response_payload=payload)
            except NfeReturnError as exc:
                _mark_event_deferred(event, error=str(exc))
                return False

            _mark_event_processed(event)
            return True

        if is_ambiguous_nfe_return_webhook(payload=payload):
            identifier = event_uuid or str(payload.get("chave") or "").strip()
            _mark_event_deferred(event, error=f"NF-e de devolução ou estorno {identifier} ambigua entre documentos.")
            return False

        nfe_item = NfeItem.objects.filter(uuid=event_uuid).select_related("request").order_by("-id").first()
        if nfe_item is None:
            _mark_event_deferred(event, error=f"Nota Fiscal {event_uuid} ainda nao foi sincronizada localmente.")
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
