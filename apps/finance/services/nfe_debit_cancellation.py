from __future__ import annotations

import hashlib
import logging
from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.finance.models.finance import (
    FiscalDocument,
    FiscalDocumentEvent,
    FiscalDocumentEventStatus,
    FiscalDocumentEventType,
    FiscalDocumentOrigin,
    FiscalDocumentPurpose,
    FiscalDocumentStatus,
    FiscalDocumentType,
    FiscalEmissionAttempt,
    FiscalEmissionDocumentKind,
    FiscalEmissionOperationType,
)
from apps.finance.services.fiscal_attempts import (
    FiscalEmissionAttemptBlocked,
    begin_emission_attempt,
    build_payload_hash,
    mark_attempt_failed,
    mark_attempt_sent,
    mark_attempt_succeeded,
    mark_attempt_uncertain,
    sanitize_fiscal_payload,
)
from apps.finance.services.nfe_debit import _build_consulta_url, _build_headers, is_nfe_debit_emission_enabled
from apps.core.infrastructure.services.webmania.webmania_auth import sanitize_webmania_setting
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


logger = logging.getLogger(__name__)
MIN_REASON_LENGTH = 15
MAX_REASON_LENGTH = 255
EVENT_PAYLOAD_TYPE = "nfe_debit_cancellation"


class NfeDebitCancellationError(Exception):
    pass


def _build_cancel_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_CANCEL_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/cancelar/"


def validate_debit_cancellation_reason(reason: str) -> str:
    normalized = str(reason or "").strip()
    if len(normalized) < MIN_REASON_LENGTH or len(normalized) > MAX_REASON_LENGTH:
        raise NfeDebitCancellationError("Informe um motivo de cancelamento entre 15 e 255 caracteres.")
    return normalized


def is_nfe_debit_eligible_for_cancellation(document: FiscalDocument | None) -> bool:
    if document is None:
        return False
    active_statuses = [FiscalDocumentEventStatus.STARTED, FiscalDocumentEventStatus.SENT, FiscalDocumentEventStatus.PROCESSING, FiscalDocumentEventStatus.UNCERTAIN]
    return bool(
        document.document_type == FiscalDocumentType.NFE
        and document.origin == FiscalDocumentOrigin.DERIVED
        and document.purpose == FiscalDocumentPurpose.DEBIT
        and document.fiscal_purpose_type == "4"
        and document.status == FiscalDocumentStatus.APPROVED
        and (str(document.access_key or "").strip() or str(document.remote_uuid or "").strip())
        and not document.events.filter(event_type=FiscalDocumentEventType.CANCELLATION, status__in=active_statuses).exists()
    )


def _assert_eligible(*, document: FiscalDocument) -> None:
    if document.document_type != FiscalDocumentType.NFE or document.origin != FiscalDocumentOrigin.DERIVED or document.purpose != FiscalDocumentPurpose.DEBIT or document.fiscal_purpose_type != "4":
        raise NfeDebitCancellationError("Cancelamento permitido somente para NF-e de débito tipo 4 emitida pelo Hunter.")
    if not is_nfe_debit_emission_enabled(workshop=document.workshop):
        raise NfeDebitCancellationError("A emissão de NF-e de débito esta desabilitada para esta oficina.")
    if document.status == FiscalDocumentStatus.CANCELED:
        raise NfeDebitCancellationError("Esta NF-e de débito já esta cancelada.")
    if document.status == FiscalDocumentStatus.UNCERTAIN:
        raise NfeDebitCancellationError("NF-e de débito em estado incerto deve ser reconciliada antes do cancelamento.")
    if document.status != FiscalDocumentStatus.APPROVED:
        raise NfeDebitCancellationError("Cancelamento permitido somente para NF-e de débito autorizada.")
    if not str(document.access_key or "").strip() and not str(document.remote_uuid or "").strip():
        raise NfeDebitCancellationError("Não foi possível cancelar NF-e de débito sem chave ou UUID.")
    active_statuses = [FiscalDocumentEventStatus.STARTED, FiscalDocumentEventStatus.SENT, FiscalDocumentEventStatus.PROCESSING, FiscalDocumentEventStatus.UNCERTAIN]
    if document.events.filter(event_type=FiscalDocumentEventType.CANCELLATION, status__in=active_statuses).exists():
        raise NfeDebitCancellationError("Já existe cancelamento da NF-e de débito em processamento ou estado incerto.")


def _build_payload(*, document: FiscalDocument, reason: str) -> dict[str, str]:
    payload = {"motivo": reason}
    if str(document.access_key or "").strip():
        payload["chave"] = str(document.access_key).strip()
    else:
        payload["uuid"] = str(document.remote_uuid).strip()
    return payload


def _idempotency_key(*, workshop_id: int, document_id: int, event_id: int) -> str:
    raw = f"{workshop_id}:{document_id}:{FiscalEmissionOperationType.NFE_DEBIT_CANCELLATION}:{event_id}:1"
    return f"{FiscalEmissionOperationType.NFE_DEBIT_CANCELLATION}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def create_debit_cancellation_event_attempt(*, document: FiscalDocument, reason: str, requested_by: Any | None, legal_confirmation: bool) -> tuple[FiscalDocumentEvent, FiscalEmissionAttempt, dict[str, str]]:
    if not legal_confirmation:
        raise NfeDebitCancellationError("Confirme explicitamente o cancelamento da NF-e de débito.")
    normalized_reason = validate_debit_cancellation_reason(reason)
    with transaction.atomic():
        locked = FiscalDocument.objects.select_for_update().select_related("workshop").get(pk=document.pk, workshop=document.workshop)
        _assert_eligible(document=locked)
        latest = locked.events.filter(event_type=FiscalDocumentEventType.CANCELLATION).order_by("-event_sequence").first()
        sequence = int(latest.event_sequence if latest else 0) + 1
        payload = _build_payload(document=locked, reason=normalized_reason)
        sanitized = sanitize_fiscal_payload(payload)
        event = FiscalDocumentEvent.objects.create(
            document=locked,
            event_type=FiscalDocumentEventType.CANCELLATION,
            event_sequence=sequence,
            event_payload_type=EVENT_PAYLOAD_TYPE,
            status=FiscalDocumentEventStatus.STARTED,
            correction_text=normalized_reason,
            request_payload=sanitized,
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
            legal_confirmation=True,
            confirmed_at=timezone.now(),
            remote_model="nfe",
        )
        attempt = begin_emission_attempt(
            workshop=locked.workshop,
            document_kind=FiscalEmissionDocumentKind.NFE,
            operation_type=FiscalEmissionOperationType.NFE_DEBIT_CANCELLATION,
            request_model=FiscalDocumentEvent.__name__,
            request_id=event.pk,
            fiscal_document=locked,
            fiscal_document_event=event,
            idempotency_key=_idempotency_key(workshop_id=locked.workshop_id, document_id=locked.pk, event_id=event.pk),
            request_payload=sanitized,
            payload_hash=build_payload_hash(sanitized),
        )
        return event, attempt, payload


def _failed(payload: dict[str, Any]) -> bool:
    return str(payload.get("status") or "").strip().lower() in {"erro", "error", "falha", "failed", "reprovado", "rejeitado"}


def _successful(payload: dict[str, Any]) -> bool:
    return not _failed(payload) and str(payload.get("status") or "").strip().lower() in {"cancelado", "cancelada", "canceled"}


def apply_debit_cancellation_payload(*, event: FiscalDocumentEvent, response_payload: dict[str, Any]) -> FiscalDocumentEvent:
    sanitized = sanitize_fiscal_payload(response_payload)
    event.response_payload = sanitized
    event.remote_uuid = str(response_payload.get("uuid") or event.remote_uuid or "").strip()
    event.remote_model = "nfe"
    event.xml_url = str(response_payload.get("xml_cancelamento") or event.xml_url or "").strip()
    event.status = FiscalDocumentEventStatus.SUCCEEDED if _successful(response_payload) else FiscalDocumentEventStatus.FAILED if _failed(response_payload) else FiscalDocumentEventStatus.PROCESSING
    event.save(update_fields=["response_payload", "remote_uuid", "remote_model", "xml_url", "status", "atualizado_em"])
    if event.status == FiscalDocumentEventStatus.SUCCEEDED:
        document = event.document
        document.status = FiscalDocumentStatus.CANCELED
        document.remote_status = FiscalDocumentStatus.CANCELED
        document.response_payload = sanitize_fiscal_payload({**(document.response_payload or {}), "cancelamento": sanitized})
        document.save(update_fields=["status", "remote_status", "response_payload", "atualizado_em"])
    return event


def _mark_uncertain(*, event: FiscalDocumentEvent, message: str, response_payload: dict[str, Any] | None = None) -> None:
    event.status = FiscalDocumentEventStatus.UNCERTAIN
    event.response_payload = sanitize_fiscal_payload({**(response_payload or {}), "error": message})
    event.save(update_fields=["status", "response_payload", "atualizado_em"])


def cancel_nfe_debit_document(*, document: FiscalDocument, reason: str, requested_by: Any | None, legal_confirmation: bool) -> FiscalDocumentEvent:
    try:
        event, attempt, payload = create_debit_cancellation_event_attempt(document=document, reason=reason, requested_by=requested_by, legal_confirmation=legal_confirmation)
    except FiscalEmissionAttemptBlocked as exc:
        raise NfeDebitCancellationError(str(exc)) from exc
    mark_attempt_sent(attempt=attempt)
    event.status = FiscalDocumentEventStatus.SENT
    event.save(update_fields=["status", "atualizado_em"])
    try:
        response = requests.put(_build_cancel_url(), json=payload, headers=_build_headers(workshop=event.document.workshop), timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = "Timeout ao cancelar NF-e de débito; estado remoto incerto."
        logger.warning("nfe_debit_cancellation_timeout", extra={"fiscal_document_event_id": event.pk, "fiscal_attempt_id": attempt.pk})
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_uncertain(event=event, message=message)
        raise NfeDebitCancellationError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao cancelar NF-e de débito", scope="nfe")
        mark_attempt_failed(attempt=attempt, error_message=message)
        event.status = FiscalDocumentEventStatus.FAILED
        event.response_payload = sanitize_fiscal_payload({"error": message})
        event.save(update_fields=["status", "response_payload", "atualizado_em"])
        raise NfeDebitCancellationError(message) from exc
    try:
        response_payload = response.json()
    except ValueError as exc:
        message = "Resposta inválida ao cancelar NF-e de débito; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_uncertain(event=event, message=message)
        raise NfeDebitCancellationError(message) from exc
    if not isinstance(response_payload, dict):
        message = "Resposta inválida ao cancelar NF-e de débito; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_uncertain(event=event, message=message)
        raise NfeDebitCancellationError(message)
    event = apply_debit_cancellation_payload(event=event, response_payload=response_payload)
    if _failed(response_payload):
        message = extract_webmania_error_message(response_payload, scope="nfe") or "Cancelamento da NF-e de débito rejeitado."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        raise NfeDebitCancellationError(message)
    if event.status != FiscalDocumentEventStatus.SUCCEEDED:
        message = "Cancelamento da NF-e de débito sem confirmação remota; estado incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        attempt.response_payload = sanitize_fiscal_payload(response_payload)
        attempt.save(update_fields=["response_payload", "atualizado_em"])
        _mark_uncertain(event=event, message=message, response_payload=response_payload)
        raise NfeDebitCancellationError(message)
    mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    return event


def _webhook_filters(payload: dict[str, Any]) -> Q:
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    filters = Q()
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid) | Q(document__remote_uuid=event_uuid)
    if access_key:
        filters |= Q(emission_attempts__remote_key=access_key) | Q(document__access_key=access_key)
    return filters


def _webhook_queryset(payload: dict[str, Any]):
    filters = _webhook_filters(payload)
    base = FiscalDocumentEvent.objects.filter(event_type=FiscalDocumentEventType.CANCELLATION, event_payload_type=EVENT_PAYLOAD_TYPE, document__document_type=FiscalDocumentType.NFE, document__purpose=FiscalDocumentPurpose.DEBIT, document__fiscal_purpose_type="4")
    return base.filter(filters).distinct() if filters else base.none()


def _all_nfe_cancellation_queryset(payload: dict[str, Any]):
    filters = _webhook_filters(payload)
    base = FiscalDocumentEvent.objects.filter(event_type=FiscalDocumentEventType.CANCELLATION, document__document_type=FiscalDocumentType.NFE)
    return base.filter(filters).distinct() if filters else base.none()


def resolve_debit_cancellation_for_webhook(*, payload: dict[str, Any]) -> FiscalDocumentEvent | None:
    matches = list(_webhook_queryset(payload).select_related("document").order_by("-pk")[:2])
    global_count = _all_nfe_cancellation_queryset(payload).values("pk")[:2].count()
    return matches[0] if len(matches) == 1 and global_count == 1 else None


def is_ambiguous_debit_cancellation_webhook(*, payload: dict[str, Any]) -> bool:
    debit_count = _webhook_queryset(payload).values("pk")[:2].count()
    return debit_count > 1 or (debit_count == 1 and _all_nfe_cancellation_queryset(payload).values("pk")[:2].count() > 1)


def reconcile_nfe_debit_cancellation(*, event: FiscalDocumentEvent) -> FiscalDocumentEvent:
    document = event.document
    identifier = str(document.remote_uuid or document.access_key or "").strip()
    if not identifier:
        raise NfeDebitCancellationError("Não foi possível consultar cancelamento sem chave ou UUID.")
    params = {"uuid": identifier} if len(identifier) != 44 else {"chave": identifier}
    try:
        response = requests.get(_build_consulta_url(), params=params, headers=_build_headers(workshop=document.workshop), timeout=30)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise NfeDebitCancellationError("Falha ao consultar cancelamento da NF-e de débito.") from exc
    if not isinstance(payload, dict):
        raise NfeDebitCancellationError("Resposta inválida da consulta da NF-e de débito.")
    return apply_debit_cancellation_payload(event=event, response_payload=payload)
