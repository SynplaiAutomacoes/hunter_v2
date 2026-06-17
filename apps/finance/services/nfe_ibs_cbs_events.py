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
from apps.finance.services.emission import build_webmania_webhook_url
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
from apps.finance.services.nfe_emission import NfeEmissionError
from apps.finance.services.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting, should_use_global_webmania_auth
from apps.finance.services.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


logger = logging.getLogger(__name__)

IBS_CBS_EVENT_112110 = "112110"
IBS_CBS_EVENT_MAX_SEQUENCE = 20
IBS_CBS_EVENT_CANCELLATION_REMOTE_CODE = "110001"


class NfeIbsCbsEventError(NfeEmissionError):
    pass


def _build_headers(*, workshop=None) -> dict[str, str]:
    try:
        if should_use_global_webmania_auth():
            return build_webmania_headers()
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfeIbsCbsEventError(str(exc)) from exc


def _build_event_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_IBS_CBS_EVENT_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/evento-ibs-cbs/"


def _build_event_cancellation_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_IBS_CBS_EVENT_CANCELLATION_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/evento-ibs-cbs/cancelar/"


def is_document_eligible_for_ibs_cbs_event_112110(document: FiscalDocument | None) -> bool:
    if document is None:
        return False
    if document.document_type == FiscalDocumentType.NFE:
        if document.origin != FiscalDocumentOrigin.LOCAL or document.purpose != FiscalDocumentPurpose.NORMAL:
            return False
    elif document.document_type == FiscalDocumentType.NFCE:
        if document.origin != FiscalDocumentOrigin.MANUAL or document.purpose != FiscalDocumentPurpose.NORMAL:
            return False
    else:
        return False
    if document.status != FiscalDocumentStatus.APPROVED:
        return False
    return bool(str(document.access_key or "").strip())


def _assert_document_eligible_for_112110(*, document: FiscalDocument) -> None:
    if document.document_type == FiscalDocumentType.NFE:
        if document.origin != FiscalDocumentOrigin.LOCAL or document.purpose != FiscalDocumentPurpose.NORMAL:
            raise NfeIbsCbsEventError("Evento IBS/CBS 112110 permitido somente para NF-e normal local nesta fase.")
    elif document.document_type == FiscalDocumentType.NFCE:
        if document.origin != FiscalDocumentOrigin.MANUAL or document.purpose != FiscalDocumentPurpose.NORMAL:
            raise NfeIbsCbsEventError("Evento IBS/CBS 112110 permitido somente para NFC-e normal manual nesta fase.")
    else:
        raise NfeIbsCbsEventError("Evento IBS/CBS 112110 permitido somente para NF-e ou NFC-e.")

    if document.status == FiscalDocumentStatus.CANCELED:
        raise NfeIbsCbsEventError("Documento cancelado nao pode receber evento IBS/CBS 112110.")
    if document.status == FiscalDocumentStatus.DENIED:
        raise NfeIbsCbsEventError("Documento denegado nao pode receber evento IBS/CBS 112110.")
    if document.status == FiscalDocumentStatus.UNCERTAIN:
        raise NfeIbsCbsEventError("Documento em estado incerto deve ser reconciliado antes do evento IBS/CBS.")
    if document.status != FiscalDocumentStatus.APPROVED:
        raise NfeIbsCbsEventError("Evento IBS/CBS 112110 permitido somente para documento autorizado.")
    if not str(document.access_key or "").strip():
        raise NfeIbsCbsEventError("Evento IBS/CBS 112110 exige chave de acesso valida.")


def _assert_no_existing_112110(*, document: FiscalDocument) -> None:
    blocking_statuses = [
        FiscalDocumentEventStatus.STARTED,
        FiscalDocumentEventStatus.SENT,
        FiscalDocumentEventStatus.PROCESSING,
        FiscalDocumentEventStatus.APPROVED,
        FiscalDocumentEventStatus.SUCCEEDED,
        FiscalDocumentEventStatus.UNCERTAIN,
    ]
    if document.events.filter(event_type=FiscalDocumentEventType.IBS_CBS, event_code=IBS_CBS_EVENT_112110, status__in=blocking_statuses).exists():
        raise NfeIbsCbsEventError("Ja existe evento IBS/CBS 112110 ativo, aprovado ou incerto para este documento.")


def _next_event_sequence(*, document: FiscalDocument, event_code: str) -> int:
    latest = document.events.filter(event_type=FiscalDocumentEventType.IBS_CBS).order_by("-event_sequence").first()
    next_sequence = int(latest.event_sequence if latest is not None else 0) + 1
    if next_sequence > IBS_CBS_EVENT_MAX_SEQUENCE:
        raise NfeIbsCbsEventError("Limite de 20 eventos IBS/CBS atingido para este documento e codigo.")
    return next_sequence


def _build_112110_payload(*, document: FiscalDocument, event_sequence: int, request: HttpRequest | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chave": str(document.access_key or "").strip(),
        "ambiente": int(str(document.environment or getattr(settings, "WEBMANIA_AMBIENT", "2") or "2")),
        "cod_evento": IBS_CBS_EVENT_112110,
        "evento": event_sequence,
    }
    notification_url = build_webmania_webhook_url(request=request)
    if notification_url:
        payload["url_notificacao"] = notification_url
    return payload


def _build_ibs_cbs_event_idempotency_key(*, workshop_id: int, document_id: int, event_code: str, event_sequence: int, request_generation: int = 1) -> str:
    raw_value = f"{workshop_id}:{document_id}:{FiscalDocumentEventType.IBS_CBS}:{event_code}:{event_sequence}:{request_generation}"
    digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()
    return f"{FiscalEmissionOperationType.NFE_IBS_CBS_EVENT}:{digest}"


def create_112110_event_attempt(*, document: FiscalDocument, requested_by: Any | None, request: HttpRequest | None = None) -> tuple[FiscalDocumentEvent, FiscalEmissionAttempt, dict[str, Any]]:
    with transaction.atomic():
        locked_document = FiscalDocument.objects.select_for_update().select_related("workshop").get(pk=document.pk)
        _assert_document_eligible_for_112110(document=locked_document)
        _assert_no_existing_112110(document=locked_document)
        event_sequence = _next_event_sequence(document=locked_document, event_code=IBS_CBS_EVENT_112110)
        payload = _build_112110_payload(document=locked_document, event_sequence=event_sequence, request=request)
        sanitized_payload = sanitize_fiscal_payload(payload)
        event = FiscalDocumentEvent.objects.create(
            document=locked_document,
            event_type=FiscalDocumentEventType.IBS_CBS,
            event_code=IBS_CBS_EVENT_112110,
            event_sequence=event_sequence,
            event_payload_type="no_specific_fields",
            status=FiscalDocumentEventStatus.STARTED,
            remote_model="ibs_cbs",
            request_payload=sanitized_payload,
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
            legal_confirmation=True,
            confirmed_at=timezone.now(),
        )
        idempotency_key = _build_ibs_cbs_event_idempotency_key(
            workshop_id=locked_document.workshop_id,
            document_id=locked_document.pk,
            event_code=IBS_CBS_EVENT_112110,
            event_sequence=event_sequence,
        )
        document_kind = FiscalEmissionDocumentKind.NFCE if locked_document.document_type == FiscalDocumentType.NFCE else FiscalEmissionDocumentKind.NFE
        attempt = begin_emission_attempt(
            workshop=locked_document.workshop,
            document_kind=document_kind,
            operation_type=FiscalEmissionOperationType.NFE_IBS_CBS_EVENT,
            request_model=FiscalDocumentEvent.__name__,
            request_id=event.pk,
            fiscal_document=locked_document,
            fiscal_document_event=event,
            idempotency_key=idempotency_key,
            request_payload=sanitized_payload,
            payload_hash=build_payload_hash(sanitized_payload),
        )
        return event, attempt, payload


def _is_failed_event_response(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    return status in {"erro", "error", "falha", "failed", "reprovado", "rejeitado"}


def _status_from_event_payload(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "").strip().lower()
    if status in {FiscalDocumentEventStatus.APPROVED, FiscalDocumentEventStatus.REPROVED, FiscalDocumentEventStatus.PROCESSING, FiscalDocumentEventStatus.SUCCEEDED, FiscalDocumentEventStatus.FAILED, FiscalDocumentEventStatus.CANCELED}:
        return status
    if _is_failed_event_response(payload):
        return FiscalDocumentEventStatus.FAILED
    return FiscalDocumentEventStatus.APPROVED if str(payload.get("uuid") or "").strip() else FiscalDocumentEventStatus.PROCESSING


def apply_ibs_cbs_event_payload(*, event: FiscalDocumentEvent, response_payload: dict[str, Any]) -> FiscalDocumentEvent:
    sanitized_payload = sanitize_fiscal_payload(response_payload)
    event.response_payload = sanitized_payload
    event.status = _status_from_event_payload(response_payload)
    event.remote_uuid = str(response_payload.get("uuid") or event.remote_uuid or "").strip()
    event.remote_event_id = str(response_payload.get("protocolo_evento") or response_payload.get("protocolo") or response_payload.get("id_evento") or event.remote_event_id or "").strip()
    event.remote_model = str(response_payload.get("modelo") or response_payload.get("model") or event.remote_model or "ibs_cbs").strip().lower()
    event.xml_url = str(response_payload.get("xml") or event.xml_url or "").strip()
    event.save(update_fields=["response_payload", "status", "remote_uuid", "remote_event_id", "remote_model", "xml_url", "atualizado_em"])
    return event


def mark_ibs_cbs_event_uncertain(*, event: FiscalDocumentEvent, error_message: str) -> None:
    event.status = FiscalDocumentEventStatus.UNCERTAIN
    event.response_payload = sanitize_fiscal_payload({"error": error_message})
    event.save(update_fields=["status", "response_payload", "atualizado_em"])


def _replay_pending_ibs_cbs_webhooks_for_uuid(*, event_uuid: str) -> None:
    if not event_uuid:
        return
    from apps.finance.services.webmania_webhooks import process_pending_webhook_events

    process_pending_webhook_events(model="ibs_cbs", event_uuid=event_uuid)


def emit_ibs_cbs_event_112110(*, document: FiscalDocument, requested_by: Any | None = None, request: HttpRequest | None = None) -> FiscalDocumentEvent:
    try:
        event, attempt, payload = create_112110_event_attempt(document=document, requested_by=requested_by, request=request)
    except FiscalEmissionAttemptBlocked as exc:
        raise NfeIbsCbsEventError(str(exc)) from exc

    headers = _build_headers(workshop=event.document.workshop)
    mark_attempt_sent(attempt=attempt)
    event.status = FiscalDocumentEventStatus.SENT
    event.save(update_fields=["status", "atualizado_em"])

    try:
        response = requests.post(_build_event_url(), json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = "Timeout ao registrar evento IBS/CBS 112110; estado remoto incerto."
        logger.warning("nfe_ibs_cbs_event_timeout", extra={"fiscal_document_event_id": event.pk, "fiscal_attempt_id": attempt.pk})
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_ibs_cbs_event_uncertain(event=event, error_message=message)
        raise NfeIbsCbsEventError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao registrar evento IBS/CBS 112110", scope="nfe")
        logger.warning("nfe_ibs_cbs_event_request_failed", extra={"fiscal_document_event_id": event.pk, "fiscal_attempt_id": attempt.pk})
        mark_attempt_failed(attempt=attempt, error_message=message)
        event.status = FiscalDocumentEventStatus.FAILED
        event.response_payload = sanitize_fiscal_payload({"error": message})
        event.save(update_fields=["status", "response_payload", "atualizado_em"])
        raise NfeIbsCbsEventError(message) from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        message = "Resposta invalida da Webmania ao registrar evento IBS/CBS 112110; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_ibs_cbs_event_uncertain(event=event, error_message=message)
        raise NfeIbsCbsEventError(message) from exc
    if not isinstance(response_payload, dict):
        message = "Resposta invalida da Webmania ao registrar evento IBS/CBS 112110; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_ibs_cbs_event_uncertain(event=event, error_message=message)
        raise NfeIbsCbsEventError(message)

    event = apply_ibs_cbs_event_payload(event=event, response_payload=response_payload)
    if _is_failed_event_response(response_payload):
        message = extract_webmania_error_message(response_payload, scope="nfe") or "Evento IBS/CBS 112110 rejeitado pela Webmania."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        raise NfeIbsCbsEventError(message)

    mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    if event.remote_uuid:
        _replay_pending_ibs_cbs_webhooks_for_uuid(event_uuid=event.remote_uuid)
    return event


def resolve_ibs_cbs_event_for_webhook(*, payload: dict[str, Any]) -> FiscalDocumentEvent | None:
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    event_sequence = payload.get("evento")
    event_code = str(payload.get("cod_evento") or IBS_CBS_EVENT_112110).strip()
    queryset = FiscalDocumentEvent.objects.filter(event_type=FiscalDocumentEventType.IBS_CBS, event_code=event_code).select_related("document")
    filters = Q()
    has_filter = False
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid)
        has_filter = True
    if access_key and str(event_sequence or "").isdigit():
        filters |= Q(document__access_key=access_key, event_sequence=int(event_sequence))
        has_filter = True
    if not has_filter:
        return None
    matches = list(queryset.filter(filters).distinct().order_by("-pk")[:2])
    if len(matches) != 1:
        return None
    return matches[0]


def is_ambiguous_ibs_cbs_event_webhook(*, payload: dict[str, Any]) -> bool:
    event_uuid = str(payload.get("uuid") or "").strip()
    access_key = str(payload.get("chave") or "").strip()
    event_sequence = payload.get("evento")
    event_code = str(payload.get("cod_evento") or IBS_CBS_EVENT_112110).strip()
    filters = Q()
    has_filter = False
    if event_uuid:
        filters |= Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid)
        has_filter = True
    if access_key and str(event_sequence or "").isdigit():
        filters |= Q(document__access_key=access_key, event_sequence=int(event_sequence))
        has_filter = True
    if not has_filter:
        return False
    return FiscalDocumentEvent.objects.filter(event_type=FiscalDocumentEventType.IBS_CBS, event_code=event_code).filter(filters).distinct().values("pk")[:2].count() > 1


def is_ibs_cbs_event_112110_cancelable(event: FiscalDocumentEvent | None) -> bool:
    if event is None:
        return False
    return (
        event.event_type == FiscalDocumentEventType.IBS_CBS
        and event.event_code == IBS_CBS_EVENT_112110
        and event.status in {FiscalDocumentEventStatus.APPROVED, FiscalDocumentEventStatus.SUCCEEDED}
        and bool(str(event.remote_uuid or "").strip())
    )


def _assert_event_cancelable_112110(*, event: FiscalDocumentEvent) -> None:
    if event.event_type != FiscalDocumentEventType.IBS_CBS or event.event_code != IBS_CBS_EVENT_112110:
        raise NfeIbsCbsEventError("Cancelamento permitido somente para evento IBS/CBS 112110 nesta fase.")
    if event.status == FiscalDocumentEventStatus.CANCELED:
        raise NfeIbsCbsEventError("Evento IBS/CBS 112110 ja esta cancelado.")
    if event.status == FiscalDocumentEventStatus.UNCERTAIN:
        raise NfeIbsCbsEventError("Evento IBS/CBS 112110 incerto deve ser reconciliado antes do cancelamento.")
    if event.status not in {FiscalDocumentEventStatus.APPROVED, FiscalDocumentEventStatus.SUCCEEDED}:
        raise NfeIbsCbsEventError("Cancelamento permitido somente para evento IBS/CBS 112110 autorizado.")
    if not str(event.remote_uuid or "").strip():
        raise NfeIbsCbsEventError("Cancelamento do evento IBS/CBS 112110 exige UUID remoto confirmado.")

    document = event.document
    if document.status in {FiscalDocumentStatus.CANCELED, FiscalDocumentStatus.DENIED, FiscalDocumentStatus.REPROVED}:
        raise NfeIbsCbsEventError("Documento fiscal base em estado final invalido nao permite cancelar evento IBS/CBS nesta fase.")

    blocking_statuses = [
        FiscalDocumentEventStatus.STARTED,
        FiscalDocumentEventStatus.SENT,
        FiscalDocumentEventStatus.PROCESSING,
        FiscalDocumentEventStatus.APPROVED,
        FiscalDocumentEventStatus.SUCCEEDED,
        FiscalDocumentEventStatus.CANCELED,
        FiscalDocumentEventStatus.UNCERTAIN,
    ]
    if event.related_cancellations.filter(event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION, status__in=blocking_statuses).exists():
        raise NfeIbsCbsEventError("Ja existe cancelamento ativo, aprovado ou incerto para este evento IBS/CBS 112110.")


def _build_112110_cancellation_payload(*, event: FiscalDocumentEvent, request: HttpRequest | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "uuid": str(event.remote_uuid or "").strip(),
    }
    environment = str(event.document.environment or "").strip()
    if environment:
        payload["ambiente"] = int(environment)
    notification_url = build_webmania_webhook_url(request=request)
    if notification_url:
        payload["url_notificacao"] = notification_url
    return payload


def _build_ibs_cbs_event_cancellation_idempotency_key(*, workshop_id: int, original_event_id: int, cancellation_event_id: int, request_generation: int = 1) -> str:
    raw_value = f"{workshop_id}:{original_event_id}:{FiscalEmissionOperationType.NFE_IBS_CBS_EVENT_CANCELLATION}:{cancellation_event_id}:{request_generation}"
    digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()
    return f"{FiscalEmissionOperationType.NFE_IBS_CBS_EVENT_CANCELLATION}:{digest}"


def create_112110_event_cancellation_attempt(*, event: FiscalDocumentEvent, requested_by: Any | None, request: HttpRequest | None = None) -> tuple[FiscalDocumentEvent, FiscalEmissionAttempt, dict[str, Any]]:
    with transaction.atomic():
        locked_event = FiscalDocumentEvent.objects.select_for_update().select_related("document", "document__workshop").get(pk=event.pk)
        _assert_event_cancelable_112110(event=locked_event)
        payload = _build_112110_cancellation_payload(event=locked_event, request=request)
        sanitized_payload = sanitize_fiscal_payload(payload)
        cancellation_event = FiscalDocumentEvent.objects.create(
            document=locked_event.document,
            related_event=locked_event,
            event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION,
            event_code=IBS_CBS_EVENT_112110,
            event_sequence=locked_event.event_sequence,
            event_payload_type="cancellation",
            status=FiscalDocumentEventStatus.STARTED,
            remote_model="ibs_cbs_cancellation",
            request_payload=sanitized_payload,
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
            legal_confirmation=True,
            confirmed_at=timezone.now(),
        )
        document_kind = FiscalEmissionDocumentKind.NFCE if locked_event.document.document_type == FiscalDocumentType.NFCE else FiscalEmissionDocumentKind.NFE
        idempotency_key = _build_ibs_cbs_event_cancellation_idempotency_key(workshop_id=locked_event.document.workshop_id, original_event_id=locked_event.pk, cancellation_event_id=cancellation_event.pk)
        attempt = begin_emission_attempt(
            workshop=locked_event.document.workshop,
            document_kind=document_kind,
            operation_type=FiscalEmissionOperationType.NFE_IBS_CBS_EVENT_CANCELLATION,
            request_model=FiscalDocumentEvent.__name__,
            request_id=cancellation_event.pk,
            fiscal_document=locked_event.document,
            fiscal_document_event=cancellation_event,
            idempotency_key=idempotency_key,
            request_payload=sanitized_payload,
            payload_hash=build_payload_hash(sanitized_payload),
        )
        return cancellation_event, attempt, payload


def _is_successful_cancellation_response(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    return status in {"aprovado", "cancelado", "cancelada", "canceled", "succeeded"}


def apply_ibs_cbs_event_cancellation_payload(*, event: FiscalDocumentEvent, response_payload: dict[str, Any]) -> FiscalDocumentEvent:
    sanitized_payload = sanitize_fiscal_payload(response_payload)
    with transaction.atomic():
        event = FiscalDocumentEvent.objects.select_for_update().get(pk=event.pk)
        event.response_payload = sanitized_payload
        event.status = _status_from_event_payload(response_payload)
        event.remote_uuid = str(response_payload.get("uuid") or event.remote_uuid or "").strip()
        event.remote_event_id = str(response_payload.get("protocolo_evento") or response_payload.get("protocolo") or response_payload.get("id_evento") or event.remote_event_id or "").strip()
        event.remote_model = str(response_payload.get("modelo") or response_payload.get("model") or event.remote_model or "ibs_cbs_cancellation").strip().lower()
        event.xml_url = str(response_payload.get("xml") or event.xml_url or "").strip()
        event.save(update_fields=["response_payload", "status", "remote_uuid", "remote_event_id", "remote_model", "xml_url", "atualizado_em"])

        if _is_successful_cancellation_response(response_payload) and event.related_event_id:
            original_event = FiscalDocumentEvent.objects.select_for_update().get(pk=event.related_event_id)
            original_event.status = FiscalDocumentEventStatus.CANCELED
            original_event.save(update_fields=["status", "atualizado_em"])
    return event


def mark_ibs_cbs_event_cancellation_uncertain(*, event: FiscalDocumentEvent, error_message: str) -> None:
    event.status = FiscalDocumentEventStatus.UNCERTAIN
    event.response_payload = sanitize_fiscal_payload({"error": error_message})
    event.save(update_fields=["status", "response_payload", "atualizado_em"])


def cancel_ibs_cbs_event_112110(*, event: FiscalDocumentEvent, requested_by: Any | None = None, request: HttpRequest | None = None) -> FiscalDocumentEvent:
    try:
        cancellation_event, attempt, payload = create_112110_event_cancellation_attempt(event=event, requested_by=requested_by, request=request)
    except FiscalEmissionAttemptBlocked as exc:
        raise NfeIbsCbsEventError(str(exc)) from exc

    headers = _build_headers(workshop=cancellation_event.document.workshop)
    mark_attempt_sent(attempt=attempt)
    cancellation_event.status = FiscalDocumentEventStatus.SENT
    cancellation_event.save(update_fields=["status", "atualizado_em"])

    try:
        response = requests.put(_build_event_cancellation_url(), json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = "Timeout ao cancelar evento IBS/CBS 112110; estado remoto incerto."
        logger.warning("nfe_ibs_cbs_event_cancellation_timeout", extra={"fiscal_document_event_id": cancellation_event.pk, "fiscal_attempt_id": attempt.pk})
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_ibs_cbs_event_cancellation_uncertain(event=cancellation_event, error_message=message)
        raise NfeIbsCbsEventError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao cancelar evento IBS/CBS 112110", scope="nfe")
        logger.warning("nfe_ibs_cbs_event_cancellation_request_failed", extra={"fiscal_document_event_id": cancellation_event.pk, "fiscal_attempt_id": attempt.pk})
        mark_attempt_failed(attempt=attempt, error_message=message)
        cancellation_event.status = FiscalDocumentEventStatus.FAILED
        cancellation_event.response_payload = sanitize_fiscal_payload({"error": message})
        cancellation_event.save(update_fields=["status", "response_payload", "atualizado_em"])
        raise NfeIbsCbsEventError(message) from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        message = "Resposta invalida da Webmania ao cancelar evento IBS/CBS 112110; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_ibs_cbs_event_cancellation_uncertain(event=cancellation_event, error_message=message)
        raise NfeIbsCbsEventError(message) from exc
    if not isinstance(response_payload, dict):
        message = "Resposta invalida da Webmania ao cancelar evento IBS/CBS 112110; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_ibs_cbs_event_cancellation_uncertain(event=cancellation_event, error_message=message)
        raise NfeIbsCbsEventError(message)

    cancellation_event = apply_ibs_cbs_event_cancellation_payload(event=cancellation_event, response_payload=response_payload)
    if _is_failed_event_response(response_payload):
        message = extract_webmania_error_message(response_payload, scope="nfe") or "Cancelamento do evento IBS/CBS 112110 rejeitado pela Webmania."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        cancellation_event.status = FiscalDocumentEventStatus.FAILED
        cancellation_event.save(update_fields=["status", "atualizado_em"])
        raise NfeIbsCbsEventError(message)

    mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    if cancellation_event.remote_uuid:
        _replay_pending_ibs_cbs_webhooks_for_uuid(event_uuid=cancellation_event.remote_uuid)
    return cancellation_event


def resolve_ibs_cbs_event_cancellation_for_webhook(*, payload: dict[str, Any]) -> FiscalDocumentEvent | None:
    event_uuid = str(payload.get("uuid") or "").strip()
    if not event_uuid:
        return None
    matches = list(
        FiscalDocumentEvent.objects.filter(event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION)
        .filter(Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid))
        .select_related("document", "related_event")
        .distinct()
        .order_by("-pk")[:2]
    )
    if len(matches) != 1:
        return None
    return matches[0]


def is_ambiguous_ibs_cbs_event_cancellation_webhook(*, payload: dict[str, Any]) -> bool:
    event_uuid = str(payload.get("uuid") or "").strip()
    if not event_uuid:
        return False
    return (
        FiscalDocumentEvent.objects.filter(event_type=FiscalDocumentEventType.IBS_CBS_CANCELLATION)
        .filter(Q(remote_uuid=event_uuid) | Q(emission_attempts__remote_uuid=event_uuid))
        .distinct()
        .values("pk")[:2]
        .count()
        > 1
    )
