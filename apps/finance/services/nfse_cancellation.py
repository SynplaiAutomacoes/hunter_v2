from __future__ import annotations

import hashlib
import logging
from typing import Any

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.finance.models.finance import FiscalEmissionAttempt, FiscalEmissionAttemptStatus, FiscalEmissionDocumentKind, FiscalEmissionOperationType, NfseCancellation, NfseItem, NfseItemStatus, NfseManualEmission, NfseRequestStatus
from apps.finance.services.fiscal_attempts import FiscalEmissionAttemptBlocked, begin_emission_attempt, build_payload_hash, mark_attempt_failed, mark_attempt_sent, mark_attempt_succeeded, mark_attempt_uncertain, sanitize_fiscal_payload
from apps.finance.services.nfse_capabilities import NfseCapabilityError, validate_nfse_cancellation_capability
from apps.finance.services.nfse_consulta import NfseConsultaError, reconcile_nfse_item
from apps.finance.services.nfse_remote_updates import parse_nfse_remote_updated_at, should_apply_nfse_update
from apps.finance.services.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting
from apps.finance.services.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


logger = logging.getLogger(__name__)

NFSE_CANCELLATION_REASONS = {
    1: "Erro na emissao",
    2: "Servico nao prestado",
    4: "Duplicidade da nota",
}


class NfseCancellationError(Exception):
    pass


def _build_cancel_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFSE_CANCEL_ENDPOINT", ""))
    if custom_endpoint:
        return custom_endpoint.rstrip("/")
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_BASE_URL", "https://api.webmania.com.br/2/")).rstrip("/")
    return f"{base_url}/nfse/cancelar"


def _build_headers(*, workshop: Any) -> dict[str, str]:
    try:
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfseCancellationError(str(exc)) from exc


def _validate_reason(reason_code: int | str) -> int:
    try:
        normalized = int(reason_code)
    except (TypeError, ValueError) as exc:
        raise NfseCancellationError("Motivo de cancelamento NFS-e invalido.") from exc
    if normalized not in NFSE_CANCELLATION_REASONS:
        raise NfseCancellationError("Motivo de cancelamento NFS-e invalido.")
    return normalized


def _existing_cancellation(item: NfseItem) -> NfseCancellation | None:
    return item.cancellations.exclude(status=FiscalEmissionAttemptStatus.FAILED).order_by("-pk").first()


def _manual_emission_for_item(item: NfseItem) -> NfseManualEmission | None:
    try:
        return item.manual_emission
    except NfseManualEmission.DoesNotExist:
        return None


def _validate_manual_cancellation_capability(*, emission: NfseManualEmission) -> None:
    capability = emission.preview.municipal_capability
    if capability.workshop_id != emission.workshop_id or capability.company_id != emission.company_id:
        raise NfseCancellationError("A capacidade municipal nao pertence a empresa/oficina da emissao manual.")
    if not capability.is_active or not capability.cancellation_enabled:
        raise NfseCancellationError("O cancelamento NFS-e esta desabilitado para o municipio configurado.")


def is_nfse_item_eligible_for_cancellation(item: NfseItem | None) -> bool:
    if item is None or item.status != NfseItemStatus.aprovado or not item.uuid:
        return False
    cancellation = _existing_cancellation(item)
    if cancellation is not None:
        return False
    manual_emission = _manual_emission_for_item(item)
    if item.request_id is None and manual_emission is None:
        return False
    if manual_emission is not None:
        try:
            _validate_manual_cancellation_capability(emission=manual_emission)
        except NfseCancellationError:
            return False
    else:
        try:
            validate_nfse_cancellation_capability(nfse_request=item.request)
        except NfseCapabilityError:
            return False
    return True


def _assert_eligible(*, item: NfseItem) -> None:
    if not item.uuid:
        raise NfseCancellationError("Nao foi possivel cancelar NFS-e sem UUID remoto.")
    manual_emission = _manual_emission_for_item(item)
    if item.request_id is None and manual_emission is None:
        raise NfseCancellationError("A NFS-e nao esta vinculada a uma requisicao legada ou emissao manual valida.")
    if str(item.status).strip().lower() == "cancelado":
        raise NfseCancellationError("Esta NFS-e ja esta cancelada.")
    if str(item.status).strip().lower() == "substituido":
        raise NfseCancellationError("NFS-e substituida nao pode ser cancelada por este fluxo.")
    if str(item.status).strip().lower() == "uncertain":
        raise NfseCancellationError("NFS-e em estado incerto deve ser reconciliada antes do cancelamento.")
    if item.status != NfseItemStatus.aprovado:
        raise NfseCancellationError("Cancelamento permitido somente para NFS-e autorizada.")
    if manual_emission is not None:
        if manual_emission.status == FiscalEmissionAttemptStatus.UNCERTAIN or manual_emission.is_uncertain:
            raise NfseCancellationError("A emissao manual NFS-e esta incerta e deve ser reconciliada antes do cancelamento.")
        _validate_manual_cancellation_capability(emission=manual_emission)
    else:
        if FiscalEmissionAttempt.objects.filter(
            workshop=item.workshop,
            document_kind=FiscalEmissionDocumentKind.NFSE,
            operation_type=FiscalEmissionOperationType.EMISSION,
            request_id=item.request_id,
            status=FiscalEmissionAttemptStatus.UNCERTAIN,
        ).exists():
            raise NfseCancellationError("A emissao NFS-e esta incerta e deve ser reconciliada antes do cancelamento.")
        try:
            validate_nfse_cancellation_capability(nfse_request=item.request)
        except NfseCapabilityError as exc:
            raise NfseCancellationError(str(exc)) from exc


def _idempotency_key(*, cancellation: NfseCancellation) -> str:
    raw = f"{cancellation.workshop_id}:{cancellation.item_id}:{FiscalEmissionOperationType.NFSE_CANCELLATION}:{cancellation.pk}:1"
    return f"{FiscalEmissionOperationType.NFSE_CANCELLATION}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def _attempt_for(cancellation: NfseCancellation) -> FiscalEmissionAttempt | None:
    return FiscalEmissionAttempt.objects.filter(
        workshop=cancellation.workshop,
        document_kind=FiscalEmissionDocumentKind.NFSE,
        operation_type=FiscalEmissionOperationType.NFSE_CANCELLATION,
        request_model=NfseCancellation.__name__,
        request_id=cancellation.pk,
    ).order_by("-pk").first()


def _create_cancellation_attempt(*, item: NfseItem, reason_code: int, requested_by: Any | None) -> tuple[NfseCancellation, FiscalEmissionAttempt, dict[str, Any]]:
    with transaction.atomic():
        locked_item = NfseItem.objects.select_for_update().get(pk=item.pk, workshop=item.workshop)
        _assert_eligible(item=locked_item)
        existing = _existing_cancellation(locked_item)
        if existing is not None:
            if existing.status == FiscalEmissionAttemptStatus.SUCCEEDED:
                raise NfseCancellationError("Esta NFS-e ja possui cancelamento concluido.")
            if existing.status == FiscalEmissionAttemptStatus.UNCERTAIN:
                raise NfseCancellationError("Ja existe cancelamento NFS-e incerto; consulte antes de qualquer nova acao.")
            raise NfseCancellationError("Ja existe cancelamento NFS-e registrado para esta nota.")

        payload = sanitize_fiscal_payload({"uuid": str(locked_item.uuid), "motivo": reason_code})
        try:
            cancellation = NfseCancellation.objects.create(
                workshop=locked_item.workshop,
                request=locked_item.request,
                item=locked_item,
                reason_code=reason_code,
                reason_label=NFSE_CANCELLATION_REASONS[reason_code],
                request_payload=payload,
                requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
            )
        except IntegrityError as exc:
            raise NfseCancellationError("Ja existe cancelamento NFS-e registrado para esta nota.") from exc

        try:
            attempt = begin_emission_attempt(
                workshop=locked_item.workshop,
                document_kind=FiscalEmissionDocumentKind.NFSE,
                operation_type=FiscalEmissionOperationType.NFSE_CANCELLATION,
                request_model=NfseCancellation.__name__,
                request_id=cancellation.pk,
                idempotency_key=_idempotency_key(cancellation=cancellation),
                request_payload=payload,
                payload_hash=build_payload_hash(payload),
            )
        except FiscalEmissionAttemptBlocked as exc:
            raise NfseCancellationError(str(exc)) from exc
        return cancellation, attempt, payload


def _is_success(payload: dict[str, Any]) -> bool:
    return str(payload.get("status") or "").strip().lower() in {"cancelado", "cancelada", "canceled"}


def _is_failure(payload: dict[str, Any]) -> bool:
    return str(payload.get("status") or "").strip().lower() in {"erro", "error", "falha", "failed", "reprovado", "rejeitado"} or bool(payload.get("error"))


def _mark_cancellation_uncertain(*, cancellation: NfseCancellation, message: str) -> None:
    cancellation.status = FiscalEmissionAttemptStatus.UNCERTAIN
    cancellation.response_payload = sanitize_fiscal_payload({"error": message})
    cancellation.save(update_fields=["status", "response_payload", "atualizado_em"])


def apply_nfse_cancellation_payload(*, cancellation: NfseCancellation, payload: dict[str, Any], update_source: str) -> NfseCancellation:
    sanitized = sanitize_fiscal_payload(payload)
    payload_uuid = str(sanitized.get("uuid") or "").strip().lower()
    if payload_uuid and payload_uuid != str(cancellation.item.uuid).strip().lower():
        raise NfseCancellationError("O retorno de cancelamento pertence a outra NFS-e.")

    cancellation.response_payload = sanitized
    cancellation.xml_url = str(sanitized.get("xml") or cancellation.xml_url or "").strip()
    if _is_success(sanitized):
        item = cancellation.item
        if not should_apply_nfse_update(model="nfse", current_status=item.status, current_remote_updated_at=item.remote_updated_at, payload=sanitized):
            raise NfseCancellationError("O cancelamento remoto nao pode ser aplicado por anti-regressao; reconcilie a NFS-e.")
        item.status = NfseItemStatus.cancelado
        item.reason = str(sanitized.get("motivo") or cancellation.reason_label).strip()
        item.last_update_source = update_source
        incoming_updated_at = parse_nfse_remote_updated_at(sanitized.get("atualizado_em") or sanitized.get("remote_updated_at"))
        update_fields = ["status", "reason", "last_update_source"]
        if incoming_updated_at is not None:
            item.remote_updated_at = incoming_updated_at
            update_fields.append("remote_updated_at")
        item.save(update_fields=update_fields)
        if cancellation.request_id:
            cancellation.request.set_status(NfseRequestStatus.CANCELED)
        cancellation.status = FiscalEmissionAttemptStatus.SUCCEEDED
        cancellation.completed_at = timezone.now()
    elif _is_failure(sanitized):
        cancellation.status = FiscalEmissionAttemptStatus.FAILED
        cancellation.completed_at = timezone.now()
    else:
        cancellation.status = FiscalEmissionAttemptStatus.UNCERTAIN
    cancellation.save(update_fields=["response_payload", "xml_url", "status", "completed_at", "atualizado_em"])
    return cancellation


def cancel_nfse_item(*, item: NfseItem, reason_code: int | str, requested_by: Any | None = None) -> NfseCancellation:
    reason = _validate_reason(reason_code)
    cancellation, attempt, payload = _create_cancellation_attempt(item=item, reason_code=reason, requested_by=requested_by)
    mark_attempt_sent(attempt=attempt)
    cancellation.status = FiscalEmissionAttemptStatus.SENT
    cancellation.sent_at = timezone.now()
    cancellation.save(update_fields=["status", "sent_at", "atualizado_em"])

    try:
        response = requests.put(_build_cancel_url(), json=payload, headers=_build_headers(workshop=item.workshop), timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = "Timeout ao cancelar NFS-e; estado remoto incerto. Consulte a nota antes de qualquer nova tentativa."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_cancellation_uncertain(cancellation=cancellation, message=message)
        raise NfseCancellationError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao cancelar Nota Fiscal de Servico", scope="nfse")
        mark_attempt_failed(attempt=attempt, error_message=message)
        cancellation.status = FiscalEmissionAttemptStatus.FAILED
        cancellation.response_payload = sanitize_fiscal_payload({"error": message})
        cancellation.completed_at = timezone.now()
        cancellation.save(update_fields=["status", "response_payload", "completed_at", "atualizado_em"])
        raise NfseCancellationError(message) from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        message = "Resposta invalida ao cancelar NFS-e; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_cancellation_uncertain(cancellation=cancellation, message=message)
        raise NfseCancellationError(message) from exc
    if not isinstance(response_payload, dict):
        message = "Resposta invalida ao cancelar NFS-e; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_cancellation_uncertain(cancellation=cancellation, message=message)
        raise NfseCancellationError(message)

    try:
        cancellation = apply_nfse_cancellation_payload(cancellation=cancellation, payload=response_payload, update_source="cancellation")
    except NfseCancellationError as exc:
        mark_attempt_uncertain(attempt=attempt, error_message=str(exc))
        _mark_cancellation_uncertain(cancellation=cancellation, message=str(exc))
        raise
    if cancellation.status == FiscalEmissionAttemptStatus.FAILED:
        message = extract_webmania_error_message(response_payload, scope="nfse") or "Cancelamento NFS-e rejeitado pela Webmania."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        raise NfseCancellationError(message)
    if cancellation.status != FiscalEmissionAttemptStatus.SUCCEEDED:
        message = "Resposta de cancelamento NFS-e sem confirmacao conclusiva; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_cancellation_uncertain(cancellation=cancellation, message=message)
        raise NfseCancellationError(message)
    mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    return cancellation


def confirm_nfse_cancellation_from_payload(*, item: NfseItem, payload: dict[str, Any], update_source: str) -> NfseCancellation | None:
    cancellation = _existing_cancellation(item)
    if cancellation is None or not _is_success(payload):
        return cancellation
    cancellation = apply_nfse_cancellation_payload(cancellation=cancellation, payload=payload, update_source=update_source)
    attempt = _attempt_for(cancellation)
    if attempt is not None and attempt.status != FiscalEmissionAttemptStatus.SUCCEEDED:
        mark_attempt_succeeded(attempt=attempt, response_payload=payload)
    return cancellation


def reconcile_nfse_cancellation(*, cancellation: NfseCancellation) -> NfseCancellation:
    if cancellation.status == FiscalEmissionAttemptStatus.SUCCEEDED:
        return cancellation
    original_xml_url = cancellation.item.xml_url
    try:
        item = reconcile_nfse_item(item=cancellation.item)
    except NfseConsultaError as exc:
        raise NfseCancellationError(str(exc)) from exc
    item.refresh_from_db()
    if item.status == NfseItemStatus.cancelado:
        payload = dict(item.raw_payload or {})
        payload.setdefault("uuid", str(item.uuid))
        payload.setdefault("status", "cancelado")
        cancellation = confirm_nfse_cancellation_from_payload(item=item, payload=payload, update_source="query") or cancellation
        if original_xml_url and item.xml_url != original_xml_url:
            item.xml_url = original_xml_url
            item.save(update_fields=["xml_url"])
        return cancellation
    return cancellation
