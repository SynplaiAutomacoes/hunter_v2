from __future__ import annotations

import hashlib
import logging
from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone

from apps.finance.models.finance import FiscalDocument, FiscalDocumentEvent, FiscalDocumentEventStatus, FiscalDocumentEventType, FiscalDocumentOrigin, FiscalDocumentPurpose, FiscalDocumentStatus, FiscalDocumentType, FiscalEmissionAttempt, FiscalEmissionDocumentKind, FiscalEmissionOperationType
from apps.finance.services.fiscal_attempts import FiscalEmissionAttemptBlocked, begin_emission_attempt, build_payload_hash, mark_attempt_failed, mark_attempt_sent, mark_attempt_succeeded, mark_attempt_uncertain, sanitize_fiscal_payload
from apps.finance.services.nfce_emission import NfceEmissionError, _build_consulta_url, _build_headers
from apps.core.infrastructure.services.webmania.webmania_auth import sanitize_webmania_setting
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


logger = logging.getLogger(__name__)

NFCE_CANCELLATION_MIN_REASON_LENGTH = 15
NFCE_CANCELLATION_MAX_REASON_LENGTH = 255


class NfceCancellationError(NfceEmissionError):
    pass


def _build_cancel_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFCE_CANCEL_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/cancelar/"


def validate_nfce_cancellation_reason(reason: str) -> str:
    normalized = str(reason or "").strip()
    if len(normalized) < NFCE_CANCELLATION_MIN_REASON_LENGTH or len(normalized) > NFCE_CANCELLATION_MAX_REASON_LENGTH:
        raise NfceCancellationError("Informe um motivo de cancelamento entre 15 e 255 caracteres.")
    return normalized


def is_nfce_document_eligible_for_cancellation(document: FiscalDocument | None) -> bool:
    if document is None:
        return False
    if document.document_type != FiscalDocumentType.NFCE or document.origin != FiscalDocumentOrigin.MANUAL or document.purpose != FiscalDocumentPurpose.NORMAL:
        return False
    if document.status != FiscalDocumentStatus.APPROVED:
        return False
    return bool(str(document.remote_uuid or "").strip() or str(document.access_key or "").strip())


def _assert_nfce_cancellation_eligible(*, document: FiscalDocument) -> None:
    if document.document_type != FiscalDocumentType.NFCE or document.origin != FiscalDocumentOrigin.MANUAL or document.purpose != FiscalDocumentPurpose.NORMAL:
        raise NfceCancellationError("Cancelamento permitido somente para NFC-e manual emitida pelo Hunter.")
    if document.status == FiscalDocumentStatus.CANCELED:
        raise NfceCancellationError("Esta NFC-e ja esta cancelada.")
    if document.status == FiscalDocumentStatus.UNCERTAIN:
        raise NfceCancellationError("NFC-e em estado incerto deve ser reconciliada antes do cancelamento.")
    if document.status != FiscalDocumentStatus.APPROVED:
        raise NfceCancellationError("Cancelamento permitido somente para NFC-e autorizada.")
    if not str(document.remote_uuid or "").strip() and not str(document.access_key or "").strip():
        raise NfceCancellationError("Nao foi possivel cancelar NFC-e sem UUID ou chave de acesso.")


def _assert_no_active_cancellation(*, document: FiscalDocument) -> None:
    active_statuses = [
        FiscalDocumentEventStatus.STARTED,
        FiscalDocumentEventStatus.SENT,
        FiscalDocumentEventStatus.PROCESSING,
        FiscalDocumentEventStatus.UNCERTAIN,
    ]
    if document.events.filter(event_type=FiscalDocumentEventType.CANCELLATION, status__in=active_statuses).exists():
        raise NfceCancellationError("Ja existe cancelamento de NFC-e em processamento ou estado incerto.")


def _next_cancellation_sequence(*, document: FiscalDocument) -> int:
    latest = document.events.filter(event_type=FiscalDocumentEventType.CANCELLATION).order_by("-event_sequence").first()
    return int(latest.event_sequence if latest is not None else 0) + 1


def _build_cancellation_payload(*, document: FiscalDocument, reason: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"motivo": reason}
    access_key = str(document.access_key or "").strip()
    if access_key:
        payload["chave"] = access_key
    else:
        payload["uuid"] = str(document.remote_uuid or "").strip()
    payload.pop("nfce_referenciada", None)
    return payload


def _build_cancellation_idempotency_key(*, workshop_id: int, document_id: int, event_id: int, request_generation: int = 1) -> str:
    raw_value = f"{workshop_id}:{document_id}:{FiscalEmissionOperationType.NFCE_CANCELLATION}:{event_id}:{request_generation}"
    digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()
    return f"{FiscalEmissionOperationType.NFCE_CANCELLATION}:{digest}"


def create_nfce_cancellation_event_attempt(*, document: FiscalDocument, reason: str, requested_by: Any | None, request: HttpRequest | None = None) -> tuple[FiscalDocumentEvent, FiscalEmissionAttempt, dict[str, Any]]:
    del request
    reason = validate_nfce_cancellation_reason(reason)
    with transaction.atomic():
        locked_document = FiscalDocument.objects.select_for_update().select_related("workshop").get(pk=document.pk)
        _assert_nfce_cancellation_eligible(document=locked_document)
        _assert_no_active_cancellation(document=locked_document)
        event_sequence = _next_cancellation_sequence(document=locked_document)
        payload = _build_cancellation_payload(document=locked_document, reason=reason)
        sanitized_payload = sanitize_fiscal_payload(payload)
        event = FiscalDocumentEvent.objects.create(
            document=locked_document,
            event_type=FiscalDocumentEventType.CANCELLATION,
            event_sequence=event_sequence,
            status=FiscalDocumentEventStatus.STARTED,
            correction_text=reason,
            request_payload=sanitized_payload,
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
            legal_confirmation=True,
            confirmed_at=timezone.now(),
        )
        idempotency_key = _build_cancellation_idempotency_key(workshop_id=locked_document.workshop_id, document_id=locked_document.pk, event_id=event.pk)
        attempt = begin_emission_attempt(
            workshop=locked_document.workshop,
            document_kind=FiscalEmissionDocumentKind.NFCE,
            operation_type=FiscalEmissionOperationType.NFCE_CANCELLATION,
            request_model=FiscalDocumentEvent.__name__,
            request_id=event.pk,
            fiscal_document=locked_document,
            fiscal_document_event=event,
            idempotency_key=idempotency_key,
            request_payload=sanitized_payload,
            payload_hash=build_payload_hash(sanitized_payload),
        )
        return event, attempt, payload


def _is_failed_cancellation_response(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    return status in {"erro", "error", "falha", "failed", "reprovado", "rejeitado"}


def _is_successful_cancellation_payload(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    if _is_failed_cancellation_response(payload):
        return False
    return status in {FiscalDocumentStatus.CANCELED, "cancelada", "canceled"}


def apply_nfce_cancellation_event_payload(*, event: FiscalDocumentEvent, response_payload: dict[str, Any]) -> FiscalDocumentEvent:
    sanitized_payload = sanitize_fiscal_payload(response_payload)
    event.response_payload = sanitized_payload
    event.remote_uuid = str(response_payload.get("uuid") or event.remote_uuid or "").strip()
    event.remote_model = str(response_payload.get("modelo") or response_payload.get("model") or event.remote_model or "nfce").strip().lower()
    event.xml_url = str(response_payload.get("xml") or response_payload.get("xml_cancelamento") or event.xml_url or "").strip()
    if _is_successful_cancellation_payload(response_payload):
        event.status = FiscalDocumentEventStatus.SUCCEEDED
    elif _is_failed_cancellation_response(response_payload):
        event.status = FiscalDocumentEventStatus.FAILED
    else:
        event.status = FiscalDocumentEventStatus.PROCESSING
    event.save(update_fields=["response_payload", "status", "remote_uuid", "remote_model", "xml_url", "atualizado_em"])

    if event.status == FiscalDocumentEventStatus.SUCCEEDED:
        document = event.document
        document.status = FiscalDocumentStatus.CANCELED
        document.remote_status = FiscalDocumentStatus.CANCELED
        if event.xml_url:
            document.response_payload = sanitize_fiscal_payload({**(document.response_payload or {}), "cancelamento": sanitized_payload})
        document.save(update_fields=["status", "remote_status", "response_payload", "atualizado_em"])
    return event


def mark_nfce_cancellation_uncertain(*, event: FiscalDocumentEvent, error_message: str) -> None:
    event.status = FiscalDocumentEventStatus.UNCERTAIN
    event.response_payload = sanitize_fiscal_payload({"error": error_message})
    event.save(update_fields=["status", "response_payload", "atualizado_em"])


def cancel_nfce_document(*, document: FiscalDocument, reason: str, requested_by: Any | None = None, request: HttpRequest | None = None) -> FiscalDocumentEvent:
    try:
        event, attempt, payload = create_nfce_cancellation_event_attempt(document=document, reason=reason, requested_by=requested_by, request=request)
    except FiscalEmissionAttemptBlocked as exc:
        raise NfceCancellationError(str(exc)) from exc

    headers = _build_headers(workshop=event.document.workshop)
    mark_attempt_sent(attempt=attempt)
    event.status = FiscalDocumentEventStatus.SENT
    event.save(update_fields=["status", "atualizado_em"])
    try:
        response = requests.put(_build_cancel_url(), json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = "Timeout ao cancelar NFC-e; estado remoto incerto."
        logger.warning("nfce_cancellation_timeout", extra={"fiscal_document_event_id": event.pk, "fiscal_attempt_id": attempt.pk})
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_nfce_cancellation_uncertain(event=event, error_message=message)
        raise NfceCancellationError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao cancelar NFC-e", scope="nfe")
        mark_attempt_failed(attempt=attempt, error_message=message)
        event.status = FiscalDocumentEventStatus.FAILED
        event.response_payload = sanitize_fiscal_payload({"error": message})
        event.save(update_fields=["status", "response_payload", "atualizado_em"])
        raise NfceCancellationError(message) from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        message = "Resposta invalida ao cancelar NFC-e; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_nfce_cancellation_uncertain(event=event, error_message=message)
        raise NfceCancellationError(message) from exc
    if not isinstance(response_payload, dict):
        message = "Resposta invalida ao cancelar NFC-e; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_nfce_cancellation_uncertain(event=event, error_message=message)
        raise NfceCancellationError(message)

    event = apply_nfce_cancellation_event_payload(event=event, response_payload=response_payload)
    if _is_failed_cancellation_response(response_payload):
        message = extract_webmania_error_message(response_payload, scope="nfe") or "Cancelamento de NFC-e rejeitado."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        raise NfceCancellationError(message)
    mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    return event


def resolve_nfce_cancellation_event_for_webhook(*, payload: dict[str, Any]) -> FiscalDocumentEvent | None:
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    queryset = FiscalDocumentEvent.objects.filter(event_type=FiscalDocumentEventType.CANCELLATION, document__document_type=FiscalDocumentType.NFCE, document__origin=FiscalDocumentOrigin.MANUAL, document__purpose=FiscalDocumentPurpose.NORMAL).select_related("document")
    filters = Q()
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid) | Q(document__remote_uuid=event_uuid)
    if access_key:
        filters |= Q(emission_attempts__remote_key=access_key) | Q(document__access_key=access_key)
    if not event_uuid and not access_key:
        return None
    matches = list(queryset.filter(filters).distinct().order_by("-pk")[:2])
    if len(matches) != 1:
        return None
    return matches[0]


def is_ambiguous_nfce_cancellation_webhook(*, payload: dict[str, Any]) -> bool:
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    if not event_uuid and not access_key:
        return False
    filters = Q()
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid) | Q(document__remote_uuid=event_uuid)
    if access_key:
        filters |= Q(emission_attempts__remote_key=access_key) | Q(document__access_key=access_key)
    return FiscalDocumentEvent.objects.filter(event_type=FiscalDocumentEventType.CANCELLATION, document__document_type=FiscalDocumentType.NFCE, document__origin=FiscalDocumentOrigin.MANUAL, document__purpose=FiscalDocumentPurpose.NORMAL).filter(filters).distinct().values("pk")[:2].count() > 1


def reconcile_nfce_cancellation_event(*, event: FiscalDocumentEvent) -> FiscalDocumentEvent:
    document = event.document
    params: dict[str, str] = {}
    if str(document.remote_uuid or "").strip():
        params["uuid"] = str(document.remote_uuid).strip()
    elif str(document.access_key or "").strip():
        params["chave"] = str(document.access_key).strip()
    else:
        raise NfceCancellationError("Nao foi possivel consultar cancelamento de NFC-e sem UUID ou chave.")
    try:
        response = requests.get(_build_consulta_url(), params=params, headers=_build_headers(workshop=document.workshop), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao consultar cancelamento de NFC-e", scope="nfe")
        raise NfceCancellationError(message) from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise NfceCancellationError("Resposta invalida da API de consulta da NFC-e.") from exc
    if not isinstance(payload, dict):
        raise NfceCancellationError("Resposta invalida da API de consulta da NFC-e.")
    return apply_nfce_cancellation_event_payload(event=event, response_payload=payload)
