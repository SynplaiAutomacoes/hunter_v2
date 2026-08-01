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
from apps.finance.services.fiscal_referenced_basis import is_credit_debit_basis_enabled
from apps.finance.services.nfe_credit import _build_consulta_url, _build_headers
from apps.core.infrastructure.services.webmania.webmania_auth import sanitize_webmania_setting
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


logger = logging.getLogger(__name__)
MIN_REASON_LENGTH = 15
MAX_REASON_LENGTH = 255


class NfeCreditCancellationError(Exception):
    pass


def _build_cancel_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_CANCEL_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/cancelar/"


def validate_credit_cancellation_reason(reason: str) -> str:
    normalized = str(reason or "").strip()
    if len(normalized) < MIN_REASON_LENGTH or len(normalized) > MAX_REASON_LENGTH:
        raise NfeCreditCancellationError("Informe um motivo de cancelamento entre 15 e 255 caracteres.")
    return normalized


def is_nfe_credit_eligible_for_cancellation(document: FiscalDocument | None) -> bool:
    if document is None:
        return False
    return bool(
        document.document_type == FiscalDocumentType.NFE
        and document.origin == FiscalDocumentOrigin.DERIVED
        and document.purpose == FiscalDocumentPurpose.CREDIT
        and document.fiscal_purpose_type == "1"
        and document.status == FiscalDocumentStatus.APPROVED
        and (str(document.access_key or "").strip() or str(document.remote_uuid or "").strip())
        and not document.events.filter(
            event_type=FiscalDocumentEventType.CANCELLATION,
            status__in=[FiscalDocumentEventStatus.STARTED, FiscalDocumentEventStatus.SENT, FiscalDocumentEventStatus.PROCESSING, FiscalDocumentEventStatus.UNCERTAIN],
        ).exists()
    )


def _assert_eligible(*, document: FiscalDocument) -> None:
    if document.document_type != FiscalDocumentType.NFE or document.origin != FiscalDocumentOrigin.DERIVED or document.purpose != FiscalDocumentPurpose.CREDIT or document.fiscal_purpose_type != "1":
        raise NfeCreditCancellationError("Cancelamento permitido somente para NF-e de crédito tipo 1 emitida pelo Hunter.")
    if not is_credit_debit_basis_enabled(workshop=document.workshop):
        raise NfeCreditCancellationError("O recurso fiscal de crédito/débito esta desabilitado para esta oficina.")
    if document.status == FiscalDocumentStatus.CANCELED:
        raise NfeCreditCancellationError("Esta NF-e de crédito já esta cancelada.")
    if document.status == FiscalDocumentStatus.UNCERTAIN:
        raise NfeCreditCancellationError("NF-e de crédito em estado incerto deve ser reconciliada antes do cancelamento.")
    if document.status != FiscalDocumentStatus.APPROVED:
        raise NfeCreditCancellationError("Cancelamento permitido somente para NF-e de crédito autorizada.")
    if not str(document.access_key or "").strip() and not str(document.remote_uuid or "").strip():
        raise NfeCreditCancellationError("Não foi possível cancelar NF-e de crédito sem chave ou UUID.")
    active_statuses = [FiscalDocumentEventStatus.STARTED, FiscalDocumentEventStatus.SENT, FiscalDocumentEventStatus.PROCESSING, FiscalDocumentEventStatus.UNCERTAIN]
    if document.events.filter(event_type=FiscalDocumentEventType.CANCELLATION, status__in=active_statuses).exists():
        raise NfeCreditCancellationError("Já existe cancelamento da NF-e de crédito em processamento ou estado incerto.")


def _build_payload(*, document: FiscalDocument, reason: str) -> dict[str, str]:
    payload = {"motivo": reason}
    if str(document.access_key or "").strip():
        payload["chave"] = str(document.access_key).strip()
    else:
        payload["uuid"] = str(document.remote_uuid).strip()
    return payload


def _idempotency_key(*, workshop_id: int, document_id: int, event_id: int) -> str:
    raw = f"{workshop_id}:{document_id}:{FiscalEmissionOperationType.NFE_CREDIT_CANCELLATION}:{event_id}:1"
    return f"{FiscalEmissionOperationType.NFE_CREDIT_CANCELLATION}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def create_credit_cancellation_event_attempt(*, document: FiscalDocument, reason: str, requested_by: Any | None, legal_confirmation: bool) -> tuple[FiscalDocumentEvent, FiscalEmissionAttempt, dict[str, str]]:
    if not legal_confirmation:
        raise NfeCreditCancellationError("Confirme explicitamente o cancelamento da NF-e de crédito.")
    reason = validate_credit_cancellation_reason(reason)
    with transaction.atomic():
        locked = FiscalDocument.objects.select_for_update().select_related("workshop").get(pk=document.pk, workshop=document.workshop)
        _assert_eligible(document=locked)
        latest = locked.events.filter(event_type=FiscalDocumentEventType.CANCELLATION).order_by("-event_sequence").first()
        sequence = int(latest.event_sequence if latest else 0) + 1
        payload = _build_payload(document=locked, reason=reason)
        sanitized = sanitize_fiscal_payload(payload)
        event = FiscalDocumentEvent.objects.create(
            document=locked,
            event_type=FiscalDocumentEventType.CANCELLATION,
            event_sequence=sequence,
            event_payload_type="nfe_credit_cancellation",
            status=FiscalDocumentEventStatus.STARTED,
            correction_text=reason,
            request_payload=sanitized,
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
            legal_confirmation=True,
            confirmed_at=timezone.now(),
            remote_model="nfe",
        )
        attempt = begin_emission_attempt(
            workshop=locked.workshop,
            document_kind=FiscalEmissionDocumentKind.NFE,
            operation_type=FiscalEmissionOperationType.NFE_CREDIT_CANCELLATION,
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


def apply_credit_cancellation_payload(*, event: FiscalDocumentEvent, response_payload: dict[str, Any]) -> FiscalDocumentEvent:
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


def _mark_uncertain(*, event: FiscalDocumentEvent, message: str) -> None:
    event.status = FiscalDocumentEventStatus.UNCERTAIN
    event.response_payload = sanitize_fiscal_payload({"error": message})
    event.save(update_fields=["status", "response_payload", "atualizado_em"])


def cancel_nfe_credit_document(*, document: FiscalDocument, reason: str, requested_by: Any | None, legal_confirmation: bool) -> FiscalDocumentEvent:
    try:
        event, attempt, payload = create_credit_cancellation_event_attempt(document=document, reason=reason, requested_by=requested_by, legal_confirmation=legal_confirmation)
    except FiscalEmissionAttemptBlocked as exc:
        raise NfeCreditCancellationError(str(exc)) from exc
    mark_attempt_sent(attempt=attempt)
    event.status = FiscalDocumentEventStatus.SENT
    event.save(update_fields=["status", "atualizado_em"])
    try:
        response = requests.put(_build_cancel_url(), json=payload, headers=_build_headers(workshop=event.document.workshop), timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = "Timeout ao cancelar NF-e de crédito; estado remoto incerto."
        logger.warning("nfe_credit_cancellation_timeout", extra={"fiscal_document_event_id": event.pk, "fiscal_attempt_id": attempt.pk})
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_uncertain(event=event, message=message)
        raise NfeCreditCancellationError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao cancelar NF-e de crédito", scope="nfe")
        mark_attempt_failed(attempt=attempt, error_message=message)
        event.status = FiscalDocumentEventStatus.FAILED
        event.response_payload = sanitize_fiscal_payload({"error": message})
        event.save(update_fields=["status", "response_payload", "atualizado_em"])
        raise NfeCreditCancellationError(message) from exc
    try:
        response_payload = response.json()
    except ValueError as exc:
        message = "Resposta inválida ao cancelar NF-e de crédito; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_uncertain(event=event, message=message)
        raise NfeCreditCancellationError(message) from exc
    if not isinstance(response_payload, dict):
        message = "Resposta inválida ao cancelar NF-e de crédito; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_uncertain(event=event, message=message)
        raise NfeCreditCancellationError(message)
    event = apply_credit_cancellation_payload(event=event, response_payload=response_payload)
    if _failed(response_payload):
        message = extract_webmania_error_message(response_payload, scope="nfe") or "Cancelamento da NF-e de crédito rejeitado."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        raise NfeCreditCancellationError(message)
    mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    return event


def _webhook_queryset(payload: dict[str, Any]):
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    filters = Q()
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid) | Q(document__remote_uuid=event_uuid)
    if access_key:
        filters |= Q(emission_attempts__remote_key=access_key) | Q(document__access_key=access_key)
    base = FiscalDocumentEvent.objects.filter(event_type=FiscalDocumentEventType.CANCELLATION, event_payload_type="nfe_credit_cancellation", document__document_type=FiscalDocumentType.NFE, document__purpose=FiscalDocumentPurpose.CREDIT, document__fiscal_purpose_type="1")
    return base.filter(filters).distinct() if filters else base.none()


def resolve_credit_cancellation_for_webhook(*, payload: dict[str, Any]) -> FiscalDocumentEvent | None:
    matches = list(_webhook_queryset(payload).select_related("document").order_by("-pk")[:2])
    return matches[0] if len(matches) == 1 else None


def is_ambiguous_credit_cancellation_webhook(*, payload: dict[str, Any]) -> bool:
    return _webhook_queryset(payload).values("pk")[:2].count() > 1


def reconcile_nfe_credit_cancellation(*, event: FiscalDocumentEvent) -> FiscalDocumentEvent:
    document = event.document
    identifier = str(document.remote_uuid or document.access_key or "").strip()
    if not identifier:
        raise NfeCreditCancellationError("Não foi possível consultar cancelamento sem chave ou UUID.")
    params = {"uuid": identifier} if len(identifier) != 44 else {"chave": identifier}
    try:
        response = requests.get(_build_consulta_url(), params=params, headers=_build_headers(workshop=document.workshop), timeout=30)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise NfeCreditCancellationError("Falha ao consultar cancelamento da NF-e de crédito.") from exc
    if not isinstance(payload, dict):
        raise NfeCreditCancellationError("Resposta inválida da consulta da NF-e de crédito.")
    return apply_credit_cancellation_payload(event=event, response_payload=payload)
