from __future__ import annotations

import hashlib
from typing import Any

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.finance.models.finance import FiscalEmissionAttempt, FiscalEmissionAttemptStatus, FiscalEmissionDocumentKind, FiscalEmissionOperationType, NfseItem, NfseItemStatus, NfseManifestation
from apps.finance.services.fiscal_attempts import FiscalEmissionAttemptBlocked, begin_emission_attempt, build_payload_hash, mark_attempt_failed, mark_attempt_sent, mark_attempt_succeeded, mark_attempt_uncertain, sanitize_fiscal_payload
from apps.finance.services.nfse_capabilities import NfseCapabilityError, validate_nfse_manifestation_capability
from apps.finance.services.nfse_consulta import NfseConsultaError, consult_nfse_uuid
from apps.finance.services.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting
from apps.finance.services.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


class NfseManifestationError(Exception):
    pass


REJECTION_REASONS = {1, 2, 3, 4, 5, 9}


def _build_manifestation_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFSE_MANIFESTATION_ENDPOINT", ""))
    if custom_endpoint:
        return custom_endpoint.rstrip("/")
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_BASE_URL", "https://api.webmania.com.br/2/")).rstrip("/")
    return f"{base_url}/nfse/manifestar"


def _build_headers(*, workshop: Any) -> dict[str, str]:
    try:
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfseManifestationError(str(exc)) from exc


def _idempotency_key(*, manifestation: NfseManifestation) -> str:
    raw = f"{manifestation.workshop_id}:{manifestation.nfse_item_id}:{manifestation.manifestation_code}:{manifestation.manifestor}:{FiscalEmissionOperationType.NFSE_MANIFESTATION}:{manifestation.pk}:1"
    return f"{FiscalEmissionOperationType.NFSE_MANIFESTATION}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def _attempt_for(manifestation: NfseManifestation) -> FiscalEmissionAttempt | None:
    return FiscalEmissionAttempt.objects.filter(workshop=manifestation.workshop, document_kind=FiscalEmissionDocumentKind.NFSE, operation_type=FiscalEmissionOperationType.NFSE_MANIFESTATION, request_model=NfseManifestation.__name__, request_id=manifestation.pk).order_by("-pk").first()


def _normalize_event(event: int | str) -> tuple[str, int]:
    try:
        code = int(event)
    except (TypeError, ValueError) as exc:
        raise NfseManifestationError("Evento de manifestacao NFS-e invalido.") from exc
    if code == 1:
        return NfseManifestation.ManifestationType.CONFIRMATION, 1
    if code == 2:
        return NfseManifestation.ManifestationType.REJECTION, 2
    raise NfseManifestationError("Evento de manifestacao NFS-e invalido.")


def _normalize_manifestor(manifestor: int | str) -> tuple[str, int]:
    try:
        code = int(manifestor)
    except (TypeError, ValueError) as exc:
        raise NfseManifestationError("Manifestador NFS-e invalido.") from exc
    if code == 1:
        return NfseManifestation.ManifestationRole.TAKER, 1
    if code == 2:
        return NfseManifestation.ManifestationRole.INTERMEDIARY, 2
    raise NfseManifestationError("Manifestador NFS-e invalido.")


def _normalize_rejection(*, event_code: int, rejection_reason: int | str | None, rejection_justification: str | None) -> tuple[int | None, str]:
    if event_code == 1:
        return None, ""
    try:
        reason = int(rejection_reason)
    except (TypeError, ValueError) as exc:
        raise NfseManifestationError("Rejeicao de NFS-e exige motivo.") from exc
    if reason not in REJECTION_REASONS:
        raise NfseManifestationError("Motivo de rejeicao NFS-e invalido.")
    justification = str(rejection_justification or "").strip()
    if reason == 9 and not (15 <= len(justification) <= 255):
        raise NfseManifestationError("Motivo 9 exige justificativa entre 15 e 255 caracteres.")
    if reason != 9 and justification:
        raise NfseManifestationError("Justificativa deve ser enviada somente para motivo 9.")
    return reason, justification


def _existing_manifestation(*, item: NfseItem, event_code: int, manifestor: int) -> NfseManifestation | None:
    return item.manifestations.filter(manifestation_code=event_code, manifestor=manifestor).exclude(status=FiscalEmissionAttemptStatus.FAILED).order_by("-pk").first()


def _assert_eligible(*, item: NfseItem) -> None:
    if item.request_id is None:
        raise NfseManifestationError("A NFS-e deve pertencer a uma requisicao local.")
    if not item.uuid:
        raise NfseManifestationError("Manifestacao exige UUID remoto da NFS-e.")
    if item.status == NfseItemStatus.cancelado:
        raise NfseManifestationError("NFS-e cancelada nao pode ser manifestada.")
    if str(item.status).strip().lower() == "substituido":
        raise NfseManifestationError("NFS-e substituida nao pode ser manifestada nesta fase.")
    if str(item.status).strip().lower() == "uncertain":
        raise NfseManifestationError("NFS-e incerta deve ser reconciliada antes da manifestacao.")
    if item.status != NfseItemStatus.aprovado:
        raise NfseManifestationError("Manifestacao permitida somente para NFS-e autorizada.")
    if FiscalEmissionAttempt.objects.filter(workshop=item.workshop, document_kind=FiscalEmissionDocumentKind.NFSE, operation_type=FiscalEmissionOperationType.EMISSION, request_id=item.request_id, status=FiscalEmissionAttemptStatus.UNCERTAIN).exists():
        raise NfseManifestationError("A emissao NFS-e esta incerta e deve ser reconciliada antes da manifestacao.")
    try:
        validate_nfse_manifestation_capability(nfse_request=item.request)
    except NfseCapabilityError as exc:
        raise NfseManifestationError(str(exc)) from exc


def is_nfse_item_eligible_for_manifestation(item: NfseItem | None) -> bool:
    if item is None:
        return False
    try:
        _assert_eligible(item=item)
    except NfseManifestationError:
        return False
    return True


def _build_payload(*, item: NfseItem, event_code: int, manifestor: int, rejection_reason: int | None, rejection_justification: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ambiente": int(getattr(item.request, "environment", 2) or 2),
        "uuid": str(item.uuid),
        "manifestador": manifestor,
        "evento": event_code,
    }
    if event_code == 2:
        payload["motivo_rejeicao"] = rejection_reason
        if rejection_reason == 9:
            payload["justificativa_rejeicao"] = rejection_justification
    return sanitize_fiscal_payload(payload)


def _create_manifestation_attempt(*, item: NfseItem, event: int | str, manifestor: int | str, rejection_reason: int | str | None, rejection_justification: str | None, created_by: Any | None) -> tuple[NfseManifestation, FiscalEmissionAttempt, dict[str, Any]]:
    manifestation_type, event_code = _normalize_event(event)
    manifestation_role, manifestor_code = _normalize_manifestor(manifestor)
    reason, justification = _normalize_rejection(event_code=event_code, rejection_reason=rejection_reason, rejection_justification=rejection_justification)
    with transaction.atomic():
        locked_item = NfseItem.objects.select_for_update().get(pk=item.pk, workshop=item.workshop)
        _assert_eligible(item=locked_item)
        existing = _existing_manifestation(item=locked_item, event_code=event_code, manifestor=manifestor_code)
        if existing is not None:
            if existing.status == FiscalEmissionAttemptStatus.UNCERTAIN:
                raise NfseManifestationError("Ja existe manifestacao NFS-e incerta; consulte antes de qualquer nova acao.")
            raise NfseManifestationError("Ja existe manifestacao NFS-e registrada para esta nota, evento e manifestador.")
        payload = _build_payload(item=locked_item, event_code=event_code, manifestor=manifestor_code, rejection_reason=reason, rejection_justification=justification)
        try:
            manifestation = NfseManifestation.objects.create(
                workshop=locked_item.workshop,
                nfse_item=locked_item,
                manifestation_type=manifestation_type,
                manifestation_code=event_code,
                manifestation_role=manifestation_role,
                manifestor=manifestor_code,
                rejection_reason=reason,
                rejection_justification=justification,
                request_payload=payload,
                created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
            )
        except IntegrityError as exc:
            raise NfseManifestationError("Ja existe manifestacao NFS-e ativa para esta nota, evento e manifestador.") from exc
        try:
            attempt = begin_emission_attempt(
                workshop=locked_item.workshop,
                document_kind=FiscalEmissionDocumentKind.NFSE,
                operation_type=FiscalEmissionOperationType.NFSE_MANIFESTATION,
                request_model=NfseManifestation.__name__,
                request_id=manifestation.pk,
                idempotency_key=_idempotency_key(manifestation=manifestation),
                request_payload=payload,
                payload_hash=build_payload_hash(payload),
            )
        except FiscalEmissionAttemptBlocked as exc:
            raise NfseManifestationError(str(exc)) from exc
        return manifestation, attempt, payload


def _status(payload: dict[str, Any]) -> str:
    return str(payload.get("status") or "").strip().lower()


def _is_success(payload: dict[str, Any]) -> bool:
    return _status(payload) in {"aprovado", "aprovada", "authorized", "processado", "manifestado"}


def _is_failure(payload: dict[str, Any]) -> bool:
    return _status(payload) in {"reprovado", "rejeitado", "erro", "error", "failed", "falha"} or bool(payload.get("error"))


def _mark_uncertain(*, manifestation: NfseManifestation, message: str) -> None:
    manifestation.status = FiscalEmissionAttemptStatus.UNCERTAIN
    manifestation.is_uncertain = True
    manifestation.response_payload = sanitize_fiscal_payload({"error": message})
    manifestation.save(update_fields=["status", "is_uncertain", "response_payload", "atualizado_em"])


@transaction.atomic
def apply_nfse_manifestation_payload(*, manifestation: NfseManifestation, payload: dict[str, Any], update_source: str) -> NfseManifestation:
    locked = NfseManifestation.objects.select_for_update().select_related("nfse_item").get(pk=manifestation.pk, workshop=manifestation.workshop)
    sanitized = sanitize_fiscal_payload(payload)
    payload_uuid = str(sanitized.get("uuid") or "").strip()
    if locked.remote_uuid and payload_uuid and str(locked.remote_uuid).lower() != payload_uuid.lower():
        raise NfseManifestationError("O retorno pertence a outra manifestacao NFS-e.")
    locked.response_payload = sanitized
    if payload_uuid:
        locked.remote_uuid = payload_uuid
    locked.remote_status = str(sanitized.get("status") or locked.remote_status or "").strip()
    locked.xml_manifestation = str(sanitized.get("xml") or sanitized.get("xml_manifestacao") or locked.xml_manifestation or "").strip()
    if _is_success(sanitized):
        locked.status = FiscalEmissionAttemptStatus.SUCCEEDED
        locked.is_uncertain = False
        locked.completed_at = timezone.now()
    elif _is_failure(sanitized):
        locked.status = FiscalEmissionAttemptStatus.FAILED
        locked.is_uncertain = False
        locked.completed_at = timezone.now()
    else:
        locked.status = FiscalEmissionAttemptStatus.UNCERTAIN
        locked.is_uncertain = True
    locked.save(update_fields=["response_payload", "remote_uuid", "remote_status", "xml_manifestation", "status", "is_uncertain", "completed_at", "atualizado_em"])
    return locked


def manifest_nfse_item(*, item: NfseItem, event: int | str, manifestor: int | str, rejection_reason: int | str | None = None, rejection_justification: str | None = None, created_by: Any | None = None) -> NfseManifestation:
    manifestation, attempt, payload = _create_manifestation_attempt(item=item, event=event, manifestor=manifestor, rejection_reason=rejection_reason, rejection_justification=rejection_justification, created_by=created_by)
    mark_attempt_sent(attempt=attempt)
    manifestation.status = FiscalEmissionAttemptStatus.SENT
    manifestation.sent_at = timezone.now()
    manifestation.save(update_fields=["status", "sent_at", "atualizado_em"])
    try:
        response = requests.post(_build_manifestation_url(), json=payload, headers=_build_headers(workshop=item.workshop), timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = "Timeout ao manifestar NFS-e; estado remoto incerto. Consulte antes de qualquer nova tentativa."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_uncertain(manifestation=manifestation, message=message)
        raise NfseManifestationError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao manifestar Nota Fiscal de Servico", scope="nfse")
        mark_attempt_failed(attempt=attempt, error_message=message)
        manifestation.status = FiscalEmissionAttemptStatus.FAILED
        manifestation.response_payload = sanitize_fiscal_payload({"error": message})
        manifestation.completed_at = timezone.now()
        manifestation.save(update_fields=["status", "response_payload", "completed_at", "atualizado_em"])
        raise NfseManifestationError(message) from exc
    try:
        response_payload = response.json()
    except ValueError as exc:
        message = "Resposta invalida ao manifestar NFS-e; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_uncertain(manifestation=manifestation, message=message)
        raise NfseManifestationError(message) from exc
    if not isinstance(response_payload, dict):
        message = "Resposta invalida ao manifestar NFS-e; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_uncertain(manifestation=manifestation, message=message)
        raise NfseManifestationError(message)
    manifestation = apply_nfse_manifestation_payload(manifestation=manifestation, payload=response_payload, update_source="manifestation")
    if manifestation.status == FiscalEmissionAttemptStatus.FAILED:
        message = extract_webmania_error_message(response_payload, scope="nfse") or "Manifestacao NFS-e rejeitada pela Webmania."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        raise NfseManifestationError(message)
    if manifestation.status != FiscalEmissionAttemptStatus.SUCCEEDED:
        message = "Resposta de manifestacao NFS-e sem confirmacao conclusiva; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_uncertain(manifestation=manifestation, message=message)
        raise NfseManifestationError(message)
    mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    return manifestation


def resolve_nfse_manifestation_for_webhook(*, payload: dict[str, Any]) -> NfseManifestation | None:
    event_uuid = str(payload.get("uuid") or "").strip()
    if not event_uuid:
        return None
    matches = list(NfseManifestation.objects.exclude(status=FiscalEmissionAttemptStatus.FAILED).filter(remote_uuid=event_uuid).order_by("pk")[:2])
    return matches[0] if len(matches) == 1 else None


def is_ambiguous_nfse_manifestation_webhook(*, payload: dict[str, Any]) -> bool:
    event_uuid = str(payload.get("uuid") or "").strip()
    return bool(event_uuid and NfseManifestation.objects.exclude(status=FiscalEmissionAttemptStatus.FAILED).filter(remote_uuid=event_uuid).count() > 1)


def confirm_nfse_manifestation_from_payload(*, manifestation: NfseManifestation, payload: dict[str, Any], update_source: str) -> NfseManifestation:
    applied = apply_nfse_manifestation_payload(manifestation=manifestation, payload=payload, update_source=update_source)
    attempt = _attempt_for(applied)
    if attempt is not None and applied.status == FiscalEmissionAttemptStatus.SUCCEEDED and attempt.status != FiscalEmissionAttemptStatus.SUCCEEDED:
        mark_attempt_succeeded(attempt=attempt, response_payload=payload)
    return applied


def reconcile_nfse_manifestation(*, manifestation: NfseManifestation) -> NfseManifestation:
    if manifestation.status == FiscalEmissionAttemptStatus.SUCCEEDED:
        return manifestation
    if not manifestation.remote_uuid:
        raise NfseManifestationError("Manifestacao incerta sem UUID remoto exige decisao administrativa; nenhum POST sera repetido.")
    try:
        payload = consult_nfse_uuid(workshop=manifestation.workshop, event_uuid=str(manifestation.remote_uuid))
    except NfseConsultaError as exc:
        raise NfseManifestationError(str(exc)) from exc
    return confirm_nfse_manifestation_from_payload(manifestation=manifestation, payload=payload, update_source="query")
