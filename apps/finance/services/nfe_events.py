from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any
from uuid import UUID

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.http import HttpRequest
from django.utils import timezone

from apps.finance.models.finance import (
    FiscalDocument,
    FiscalDocumentEvent,
    FiscalDocumentEventStatus,
    FiscalDocumentEventType,
    FiscalDocumentStatus,
    FiscalDocumentType,
    FiscalEmissionAttempt,
    FiscalEmissionDocumentKind,
    FiscalEmissionOperationType,
    NfeItem,
    NfeItemStatus,
)
from apps.core.infrastructure.services.webmania.emission import build_webmania_webhook_url
from apps.finance.services.fiscal_attempts import (
    FiscalEmissionAttemptBlocked,
    begin_emission_attempt,
    build_fiscal_operation_idempotency_key,
    build_payload_hash,
    mark_attempt_failed,
    mark_attempt_sent,
    mark_attempt_succeeded,
    mark_attempt_uncertain,
    sanitize_fiscal_payload,
)
from apps.core.infrastructure.services.webmania.nfe_emission import NfeEmissionError
from apps.core.infrastructure.services.webmania.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting, should_use_global_webmania_auth
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


logger = logging.getLogger(__name__)

CCE_MAX_SEQUENCE = 20
CCE_MIN_TEXT_LENGTH = 15
CCE_MAX_TEXT_LENGTH = 1000
CCE_PROHIBITED_TEXT_PATTERNS = (
    r"\bvalor(?:es)?\b",
    r"\bpreco\b",
    r"\bprecos\b",
    r"\bquantidade\b",
    r"\bproduto\b",
    r"\bprodutos\b",
    r"\bdestinatario\b",
    r"\btomador\b",
    r"\bremetente\b",
    r"\bdata\s+(?:de\s+)?emissao\b",
    r"\bdata\s+(?:de\s+)?saida\b",
    r"\bbase\s+de\s+calculo\b",
    r"\baliquota\b",
    r"\bimposto\b",
    r"\bimpostos\b",
    r"\bicms\b",
    r"\bipi\b",
    r"\bpis\b",
    r"\bcofins\b",
    r"\bissqn\b",
    r"\bcfop\b",
    r"\bncm\b",
    r"\bserie\b",
    r"\bnumero\b",
)


class NfeCorrectionError(NfeEmissionError):
    pass


def _build_headers(*, workshop=None) -> dict[str, str]:
    try:
        if should_use_global_webmania_auth():
            return build_webmania_headers()
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfeCorrectionError(str(exc)) from exc


def _build_cce_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_CCE_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"

    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/cartacorrecao/"


def _build_cce_consulta_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_CONSULTA_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"

    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/consulta/"


def validate_correction_text(correction_text: str) -> str:
    normalized = str(correction_text or "").strip()
    if len(normalized) < CCE_MIN_TEXT_LENGTH or len(normalized) > CCE_MAX_TEXT_LENGTH:
        raise NfeCorrectionError("Informe uma correcao entre 15 e 1000 caracteres.")
    normalized_search_text = _normalize_cce_search_text(normalized)
    if any(re.search(pattern, normalized_search_text) for pattern in CCE_PROHIBITED_TEXT_PATTERNS):
        raise NfeCorrectionError("A carta de correcao nao pode alterar valores, impostos, produtos, quantidades, destinatario, datas, serie, numero ou outros dados fiscais essenciais da NF-e.")
    return normalized


def _normalize_cce_search_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents.lower()).strip()


def is_nfe_item_eligible_for_cce(item: NfeItem | None) -> bool:
    if item is None:
        return False
    if str(getattr(item, "status", "")).strip().lower() != NfeItemStatus.aprovado:
        return False
    return bool(str(getattr(item, "access_key", "") or "").strip() or str(getattr(item, "uuid", "") or "").strip())


def has_active_cce_event_for_nfe_item(*, item: NfeItem | None) -> bool:
    if item is None:
        return False
    return FiscalDocumentEvent.objects.filter(
        document__legacy_nfe_item=item,
        document__workshop=item.workshop,
        event_type=FiscalDocumentEventType.CCE,
        status__in=[
            FiscalDocumentEventStatus.STARTED,
            FiscalDocumentEventStatus.SENT,
            FiscalDocumentEventStatus.PROCESSING,
            FiscalDocumentEventStatus.UNCERTAIN,
        ],
    ).exists()


def ensure_fiscal_document_for_nfe_item(*, item: NfeItem) -> FiscalDocument:
    if not is_nfe_item_eligible_for_cce(item):
        raise NfeCorrectionError("Carta de correcao permitida somente para NF-e autorizada com chave de acesso ou UUID valido.")

    workshop = item.workshop
    account = getattr(workshop, "account", None)
    defaults = {
        "account": account,
        "document_type": FiscalDocumentType.NFE,
        "remote_uuid": str(item.uuid or "").strip(),
        "access_key": str(item.access_key or "").strip(),
        "series": str(item.series or "").strip(),
        "number": str(item.number or "").strip(),
        "environment": str(getattr(settings, "WEBMANIA_AMBIENT", "2") or "2").strip(),
        "status": FiscalDocumentStatus.APPROVED,
        "remote_status": str(item.status or "").strip(),
    }
    try:
        document, created = FiscalDocument.objects.get_or_create(
            workshop=workshop,
            legacy_nfe_item=item,
            defaults=defaults,
        )
    except IntegrityError:
        document = FiscalDocument.objects.get(workshop=workshop, legacy_nfe_item=item)
        created = False
    if not created:
        changed_fields: list[str] = []
        for field_name, value in defaults.items():
            if getattr(document, field_name) != value:
                setattr(document, field_name, value)
                changed_fields.append(field_name)
        if changed_fields:
            changed_fields.append("atualizado_em")
            document.save(update_fields=changed_fields)
    return document


def _next_cce_sequence(*, document: FiscalDocument) -> int:
    current_max = document.events.filter(event_type=FiscalDocumentEventType.CCE).aggregate(max_sequence=Max("event_sequence"))["max_sequence"] or 0
    next_sequence = int(current_max) + 1
    if next_sequence > CCE_MAX_SEQUENCE:
        raise NfeCorrectionError("Limite de 20 cartas de correcao atingido para esta NF-e.")
    return next_sequence


def _assert_no_active_cce_attempt(*, document: FiscalDocument) -> None:
    active_statuses = [
        FiscalDocumentEventStatus.STARTED,
        FiscalDocumentEventStatus.SENT,
        FiscalDocumentEventStatus.PROCESSING,
        FiscalDocumentEventStatus.UNCERTAIN,
    ]
    if document.events.filter(event_type=FiscalDocumentEventType.CCE, status__in=active_statuses).exists():
        raise NfeCorrectionError("Ja existe uma carta de correcao em processamento ou estado incerto para esta NF-e.")


def _build_cce_payload(*, document: FiscalDocument, correction_text: str, event_sequence: int, request: HttpRequest | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "correcao": correction_text,
        "ambiente": int(str(document.environment or getattr(settings, "WEBMANIA_AMBIENT", "2") or "2")),
        "evento": event_sequence,
    }
    access_key = str(document.access_key or "").strip()
    if access_key:
        payload["chave"] = access_key
    else:
        payload["uuid"] = str(document.remote_uuid or "").strip()

    notification_url = build_webmania_webhook_url(request=request)
    if notification_url:
        payload["url_notificacao"] = notification_url
    return payload


def reserve_cce_event_attempt(*, document: FiscalDocument, correction_text: str, requested_by: Any | None, request: HttpRequest | None = None) -> tuple[FiscalDocumentEvent, FiscalEmissionAttempt, dict[str, Any]]:
    correction_text = validate_correction_text(correction_text)

    with transaction.atomic():
        locked_document = FiscalDocument.objects.select_for_update().select_related("workshop").get(pk=document.pk)
        _assert_no_active_cce_attempt(document=locked_document)
        event_sequence = _next_cce_sequence(document=locked_document)
        payload = _build_cce_payload(document=locked_document, correction_text=correction_text, event_sequence=event_sequence, request=request)
        sanitized_payload = sanitize_fiscal_payload(payload)

        event = FiscalDocumentEvent.objects.create(
            document=locked_document,
            event_type=FiscalDocumentEventType.CCE,
            event_sequence=event_sequence,
            status=FiscalDocumentEventStatus.STARTED,
            correction_text=correction_text,
            request_payload=sanitized_payload,
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
            legal_confirmation=True,
            confirmed_at=timezone.now(),
        )

        idempotency_key = build_fiscal_operation_idempotency_key(
            workshop_id=locked_document.workshop_id,
            document_id=locked_document.pk,
            operation_type=FiscalEmissionOperationType.CCE,
            sequence=event_sequence,
        )
        attempt = begin_emission_attempt(
            workshop=locked_document.workshop,
            document_kind=FiscalEmissionDocumentKind.NFE,
            operation_type=FiscalEmissionOperationType.CCE,
            request_model=FiscalDocumentEvent.__name__,
            request_id=event.pk,
            fiscal_document=locked_document,
            fiscal_document_event=event,
            idempotency_key=idempotency_key,
            request_payload=sanitized_payload,
            payload_hash=build_payload_hash(sanitized_payload),
        )
        return event, attempt, payload


def _is_failed_cce_response(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    return status in {"erro", "error", "falha", "failed", "reprovado", "rejeitado"}


def _status_from_cce_payload(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "").strip().lower()
    if status in {FiscalDocumentEventStatus.APPROVED, FiscalDocumentEventStatus.REPROVED, FiscalDocumentEventStatus.PROCESSING}:
        return status
    if _is_failed_cce_response(payload):
        return FiscalDocumentEventStatus.FAILED
    return FiscalDocumentEventStatus.APPROVED if str(payload.get("uuid") or "").strip() else FiscalDocumentEventStatus.PROCESSING


def apply_cce_event_payload(*, event: FiscalDocumentEvent, response_payload: dict[str, Any]) -> FiscalDocumentEvent:
    sanitized_payload = sanitize_fiscal_payload(response_payload)
    event.response_payload = sanitized_payload
    event.status = _status_from_cce_payload(response_payload)
    event.remote_uuid = str(response_payload.get("uuid") or event.remote_uuid or "").strip()
    event.remote_event_id = str(
        response_payload.get("protocolo")
        or response_payload.get("protocolo_evento")
        or response_payload.get("protocol")
        or response_payload.get("id_evento")
        or response_payload.get("nProt")
        or event.remote_event_id
        or ""
    ).strip()
    event.remote_model = str(response_payload.get("modelo") or response_payload.get("model") or event.remote_model or "cce").strip().lower()
    event.xml_url = str(response_payload.get("xml") or event.xml_url or "").strip()
    event.dacce_url = str(response_payload.get("dacce") or event.dacce_url or "").strip()
    event.save(update_fields=["response_payload", "status", "remote_uuid", "remote_event_id", "remote_model", "xml_url", "dacce_url", "atualizado_em"])
    return event


def _cce_attempt_for_event(*, event: FiscalDocumentEvent) -> FiscalEmissionAttempt | None:
    return event.emission_attempts.filter(operation_type=FiscalEmissionOperationType.CCE).order_by("-pk").first()


def confirm_cce_event_from_payload(*, event: FiscalDocumentEvent, response_payload: dict[str, Any]) -> FiscalDocumentEvent:
    event = apply_cce_event_payload(event=event, response_payload=response_payload)
    attempt = _cce_attempt_for_event(event=event)
    if attempt is None:
        return event

    if event.status in {FiscalDocumentEventStatus.APPROVED, FiscalDocumentEventStatus.SUCCEEDED}:
        mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    elif event.status in {FiscalDocumentEventStatus.REPROVED, FiscalDocumentEventStatus.FAILED}:
        message = extract_webmania_error_message(response_payload, scope="nfe") or "Carta de correcao rejeitada."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
    return event


def _resolve_cce_remote_uuid(*, event: FiscalDocumentEvent) -> str:
    remote_uuid = str(event.remote_uuid or "").strip()
    if not remote_uuid:
        attempt = _cce_attempt_for_event(event=event)
        if attempt is not None:
            remote_uuid = str(attempt.remote_uuid or "").strip()
    if not remote_uuid:
        raise NfeCorrectionError("Carta de correcao em estado incerto sem UUID remoto. Aguarde o webhook antes de tentar novamente.")
    _parse_cce_uuid(remote_uuid, error_message="Carta de correcao em estado incerto com UUID remoto invalido. Aguarde identificacao segura antes de reconciliar.")
    return remote_uuid


def _parse_cce_uuid(value: str, *, error_message: str) -> UUID:
    try:
        return UUID(str(value or "").strip())
    except (AttributeError, TypeError, ValueError) as exc:
        raise NfeCorrectionError(error_message) from exc


def validate_cce_payload_identity(
    *,
    event: FiscalDocumentEvent,
    payload: dict[str, Any],
    expected_uuid: str | None = None,
    require_uuid: bool = False,
    require_sequence: bool = False,
    require_document_key: bool = False,
) -> None:
    payload_uuid = str(payload.get("uuid") or "").strip()
    payload_model = str(payload.get("modelo") or payload.get("model") or "").strip().lower()
    if payload_model != "cce":
        raise NfeCorrectionError("A consulta retornou um documento diferente da carta de correcao esperada.")

    if require_uuid and not payload_uuid:
        raise NfeCorrectionError("A resposta da carta de correcao nao possui UUID remoto seguro.")
    if payload_uuid:
        parsed_payload_uuid = _parse_cce_uuid(payload_uuid, error_message="A resposta da carta de correcao possui UUID remoto invalido.")
        if expected_uuid and parsed_payload_uuid != _parse_cce_uuid(expected_uuid, error_message="A carta de correcao local possui UUID remoto invalido."):
            raise NfeCorrectionError("A consulta retornou um documento diferente da carta de correcao esperada.")

    payload_sequence = payload.get("evento")
    if require_sequence and payload_sequence in (None, ""):
        raise NfeCorrectionError("A resposta da carta de correcao nao possui sequencia segura.")
    if payload_sequence not in (None, "") and (not str(payload_sequence).isdigit() or int(payload_sequence) != event.event_sequence):
        raise NfeCorrectionError("A consulta retornou uma sequencia de carta de correcao diferente da esperada.")

    payload_key = str(payload.get("chave") or "").strip()
    document_key = str(event.document.access_key or "").strip()
    if require_document_key and document_key and not payload_key:
        raise NfeCorrectionError("A resposta da carta de correcao nao identifica a NF-e relacionada.")
    if payload_key and document_key and payload_key != document_key:
        raise NfeCorrectionError("A consulta retornou uma carta de correcao vinculada a outra NF-e.")


def _validate_cce_consulta_identity(*, event: FiscalDocumentEvent, payload: dict[str, Any], expected_uuid: str) -> None:
    validate_cce_payload_identity(event=event, payload=payload, expected_uuid=expected_uuid, require_uuid=True)


def consult_cce_event(*, event: FiscalDocumentEvent) -> dict[str, Any]:
    expected_uuid = _resolve_cce_remote_uuid(event=event)
    try:
        response = requests.get(
            _build_cce_consulta_url(),
            params={"uuid": expected_uuid},
            headers=_build_headers(workshop=event.document.workshop),
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao consultar carta de correcao", scope="nfe")
        raise NfeCorrectionError(message) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise NfeCorrectionError("Resposta invalida da API de consulta da carta de correcao.") from exc
    if not isinstance(payload, dict):
        raise NfeCorrectionError("Resposta invalida da API de consulta da carta de correcao.")

    error_message = extract_webmania_error_message(payload.get("error") or payload.get("msg") or payload.get("message"), scope="nfe")
    if error_message:
        raise NfeCorrectionError(error_message)
    _validate_cce_consulta_identity(event=event, payload=payload, expected_uuid=expected_uuid)
    return payload


def reconcile_cce_event(*, event: FiscalDocumentEvent) -> FiscalDocumentEvent:
    payload = consult_cce_event(event=event)
    return confirm_cce_event_from_payload(event=event, response_payload=payload)


def mark_cce_event_uncertain(*, event: FiscalDocumentEvent, error_message: str, response_payload: dict[str, Any] | None = None) -> None:
    event.status = FiscalDocumentEventStatus.UNCERTAIN
    uncertain_payload = dict(response_payload) if response_payload is not None else {"error": error_message}
    if response_payload is not None:
        uncertain_payload["reconciliation_error"] = error_message
    event.response_payload = sanitize_fiscal_payload(uncertain_payload)
    event.save(update_fields=["status", "response_payload", "atualizado_em"])


def _replay_pending_cce_webhooks_for_uuid(*, event_uuid: str) -> None:
    if not event_uuid:
        return
    from apps.core.infrastructure.services.webmania.webmania_webhooks import process_pending_webhook_events

    process_pending_webhook_events(model="cce", event_uuid=event_uuid)


def emit_nfe_correction(*, nfe_item: NfeItem, correction_text: str, requested_by: Any | None = None, request: HttpRequest | None = None) -> FiscalDocumentEvent:
    document = ensure_fiscal_document_for_nfe_item(item=nfe_item)
    try:
        event, attempt, payload = reserve_cce_event_attempt(document=document, correction_text=correction_text, requested_by=requested_by, request=request)
    except FiscalEmissionAttemptBlocked as exc:
        raise NfeCorrectionError(str(exc)) from exc

    headers = _build_headers(workshop=document.workshop)
    mark_attempt_sent(attempt=attempt)
    event.status = FiscalDocumentEventStatus.SENT
    event.save(update_fields=["status", "atualizado_em"])

    try:
        response = requests.post(_build_cce_url(), json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = "Timeout ao emitir carta de correcao; estado remoto incerto."
        logger.warning("nfe_cce_timeout", extra={"fiscal_document_event_id": event.pk, "fiscal_attempt_id": attempt.pk})
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_cce_event_uncertain(event=event, error_message=message)
        raise NfeCorrectionError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao emitir carta de correcao", scope="nfe")
        logger.warning("nfe_cce_request_failed", extra={"fiscal_document_event_id": event.pk, "fiscal_attempt_id": attempt.pk})
        mark_attempt_failed(attempt=attempt, error_message=message)
        event.status = FiscalDocumentEventStatus.FAILED
        event.response_payload = sanitize_fiscal_payload({"error": message})
        event.save(update_fields=["status", "response_payload", "atualizado_em"])
        raise NfeCorrectionError(message) from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        message = "Resposta invalida ao emitir carta de correcao; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_cce_event_uncertain(event=event, error_message=message)
        raise NfeCorrectionError(message) from exc

    if not isinstance(response_payload, dict):
        message = "Resposta invalida ao emitir carta de correcao; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_cce_event_uncertain(event=event, error_message=message)
        raise NfeCorrectionError(message)

    if _is_failed_cce_response(response_payload):
        event = apply_cce_event_payload(event=event, response_payload=response_payload)
        message = extract_webmania_error_message(response_payload, scope="nfe") or "Carta de correcao rejeitada."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        raise NfeCorrectionError(message)

    try:
        validate_cce_payload_identity(event=event, payload=response_payload, require_uuid=True, require_sequence=True)
    except NfeCorrectionError as exc:
        message = f"Resposta inconsistente ao emitir carta de correcao; estado remoto incerto. {exc}"
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        mark_cce_event_uncertain(event=event, error_message=message, response_payload=response_payload)
        raise NfeCorrectionError(message) from exc

    event = apply_cce_event_payload(event=event, response_payload=response_payload)
    mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    if event.remote_uuid:
        _replay_pending_cce_webhooks_for_uuid(event_uuid=event.remote_uuid)
    return event
