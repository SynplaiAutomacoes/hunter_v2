from __future__ import annotations

import hashlib
from typing import Any

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.finance.models.finance import FiscalEmissionAttempt, FiscalEmissionAttemptStatus, FiscalEmissionDocumentKind, FiscalEmissionOperationType, FiscalProductPreviewStatus, NfseItem, NfseItemStatus, NfseManualEmission, NfseManualEmissionPreview, NfseRequest, WebmaniaCompany
from apps.finance.services.fiscal_attempts import FiscalEmissionAttemptBlocked, begin_emission_attempt, build_payload_hash, mark_attempt_failed, mark_attempt_sent, mark_attempt_succeeded, mark_attempt_uncertain, sanitize_fiscal_payload
from apps.finance.services.mappers import map_item_payload
from apps.core.infrastructure.services.webmania.nfse_consulta import NfseConsultaError, consult_nfse_uuid
from apps.core.infrastructure.services.webmania.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


class NfseManualEmissionError(Exception):
    pass


def _build_manual_emission_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFSE_EMISSION_ENDPOINT", ""))
    if custom_endpoint:
        return custom_endpoint.rstrip("/")
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_BASE_URL", "https://api.webmania.com.br/2/")).rstrip("/")
    return f"{base_url}/nfse/emissao"


def _build_headers(*, workshop: Any) -> dict[str, str]:
    try:
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfseManualEmissionError(str(exc)) from exc


def is_nfse_manual_emission_enabled(*, workshop: Any) -> bool:
    return WebmaniaCompany.objects.filter(workshop=workshop, nfse_manual_emission_enabled=True).exists()


def _idempotency_key(*, emission: NfseManualEmission) -> str:
    raw = f"{emission.workshop_id}:{emission.preview_id}:{FiscalEmissionOperationType.NFSE_MANUAL_EMISSION}:{emission.pk}:1"
    return f"{FiscalEmissionOperationType.NFSE_MANUAL_EMISSION}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"


def _attempt_for(emission: NfseManualEmission) -> FiscalEmissionAttempt | None:
    return FiscalEmissionAttempt.objects.filter(
        workshop=emission.workshop,
        document_kind=FiscalEmissionDocumentKind.NFSE,
        operation_type=FiscalEmissionOperationType.NFSE_MANUAL_EMISSION,
        request_model=NfseManualEmission.__name__,
        request_id=emission.pk,
    ).order_by("-pk").first()


def _status(payload: dict[str, Any]) -> str:
    return str(payload.get("status") or "").strip().lower()


def _is_success(payload: dict[str, Any]) -> bool:
    return _status(payload) in {"aprovado", "aprovada", "authorized"}


def _is_processing(payload: dict[str, Any]) -> bool:
    return _status(payload) in {"processando", "processing", "contingencia", "agendado", "processado"}


def _is_failure(payload: dict[str, Any]) -> bool:
    return _status(payload) in {"reprovado", "rejeitado", "erro", "error", "failed", "falha"} or bool(payload.get("error"))


def _assert_company_configured(company: WebmaniaCompany) -> None:
    if not str(company.webmania_company_id or company.bearer_access_token or company.consumer_key or "").strip():
        raise NfseManualEmissionError("Empresa emissora nao esta configurada.")


def _assert_payload_contract(preview: NfseManualEmissionPreview) -> None:
    payload = preview.request_payload
    if not isinstance(payload, dict) or not payload:
        raise NfseManualEmissionError("Preview aprovada sem payload.")
    if payload.get("ambiente") != int(preview.environment):
        raise NfseManualEmissionError("Payload aprovado diverge do ambiente da preview.")
    rps_list = payload.get("rps")
    if not isinstance(rps_list, list) or len(rps_list) != 1 or not isinstance(rps_list[0], dict):
        raise NfseManualEmissionError("Payload aprovado deve conter exatamente um RPS congelado.")
    rps = rps_list[0]
    if rps.get("numero") != preview.rps_number or rps.get("serie") != preview.rps_series:
        raise NfseManualEmissionError("Payload aprovado diverge do numero/serie do RPS.")
    if not isinstance(rps.get("servico"), dict) or not rps["servico"]:
        raise NfseManualEmissionError("Payload aprovado sem servico.")
    if not isinstance(rps.get("tomador"), dict) or not rps["tomador"]:
        raise NfseManualEmissionError("Payload aprovado sem tomador.")


def _assert_rps_available(*, preview: NfseManualEmissionPreview) -> None:
    reserved_request = NfseRequest.objects.filter(
        workshop=preview.workshop,
        reserved_rps_number=preview.rps_number,
        reserved_rps_series=preview.rps_series,
    ).exists()
    existing_item = NfseItem.objects.filter(
        workshop=preview.workshop,
        rps_number=str(preview.rps_number),
        rps_series=preview.rps_series,
    ).exclude(status__in=[NfseItemStatus.reprovado]).exists()
    existing_emission = NfseManualEmission.objects.filter(
        company=preview.company,
        environment=preview.environment,
        rps_number=preview.rps_number,
        rps_series=preview.rps_series,
    ).exclude(status=FiscalEmissionAttemptStatus.FAILED).exists()
    if reserved_request or existing_item or existing_emission:
        raise NfseManualEmissionError("Ja existe NFS-e manual ou RPS local conhecido para esta empresa/oficina/ambiente.")


def _validate_eligibility(*, preview: NfseManualEmissionPreview) -> None:
    if not preview.is_approved or preview.validation_status != FiscalProductPreviewStatus.APPROVED:
        raise NfseManualEmissionError("A emissao manual exige preview aprovada.")
    if not is_nfse_manual_emission_enabled(workshop=preview.workshop):
        raise NfseManualEmissionError("A emissao manual NFS-e esta desabilitada para esta oficina.")
    _assert_company_configured(preview.company)
    capability = preview.municipal_capability
    if not capability.is_active or not capability.emission_enabled or not capability.manual_emission_enabled:
        raise NfseManualEmissionError("A capacidade municipal nao permite emissao manual NFS-e.")
    if capability.workshop_id != preview.workshop_id or capability.company_id != preview.company_id:
        raise NfseManualEmissionError("A capacidade municipal nao pertence a empresa/oficina da preview.")
    if preview.environment not in {"1", "2"} or preview.rps_number <= 0 or not preview.rps_series.strip():
        raise NfseManualEmissionError("Ambiente, numero e serie do RPS sao obrigatorios.")
    _assert_payload_contract(preview)


def is_nfse_manual_emission_eligible(preview: NfseManualEmissionPreview | None) -> bool:
    if preview is None:
        return False
    try:
        _validate_eligibility(preview=preview)
    except NfseManualEmissionError:
        return False
    return not NfseManualEmission.objects.filter(preview=preview).exclude(status=FiscalEmissionAttemptStatus.FAILED).exists()


def _create_intention(*, preview: NfseManualEmissionPreview, created_by: Any | None) -> tuple[NfseManualEmission, FiscalEmissionAttempt, dict[str, Any]]:
    with transaction.atomic():
        locked_preview = (
            NfseManualEmissionPreview.objects.select_for_update(of=("self",))
            .select_related("company", "municipal_capability")
            .get(pk=preview.pk, workshop=preview.workshop)
        )
        _validate_eligibility(preview=locked_preview)
        _assert_rps_available(preview=locked_preview)
        payload = sanitize_fiscal_payload(locked_preview.request_payload)
        try:
            emission = NfseManualEmission.objects.create(
                workshop=locked_preview.workshop,
                company=locked_preview.company,
                preview=locked_preview,
                environment=locked_preview.environment,
                rps_number=locked_preview.rps_number,
                rps_series=locked_preview.rps_series,
                request_payload=payload,
                created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
            )
        except IntegrityError as exc:
            raise NfseManualEmissionError("Ja existe emissao manual registrada para esta preview ou RPS.") from exc
        try:
            attempt = begin_emission_attempt(
                workshop=locked_preview.workshop,
                document_kind=FiscalEmissionDocumentKind.NFSE,
                operation_type=FiscalEmissionOperationType.NFSE_MANUAL_EMISSION,
                request_model=NfseManualEmission.__name__,
                request_id=emission.pk,
                idempotency_key=_idempotency_key(emission=emission),
                request_payload=payload,
                payload_hash=build_payload_hash(payload),
            )
        except FiscalEmissionAttemptBlocked as exc:
            raise NfseManualEmissionError(str(exc)) from exc
        return emission, attempt, payload


def _mark_uncertain(*, emission: NfseManualEmission, message: str) -> None:
    emission.status = FiscalEmissionAttemptStatus.UNCERTAIN
    emission.is_uncertain = True
    emission.response_payload = sanitize_fiscal_payload({"error": message})
    emission.save(update_fields=["status", "is_uncertain", "response_payload", "atualizado_em"])


@transaction.atomic
def apply_nfse_manual_emission_payload(*, emission: NfseManualEmission, payload: dict[str, Any], update_source: str) -> NfseManualEmission:
    locked = NfseManualEmission.objects.select_for_update().select_related("preview").get(pk=emission.pk, workshop=emission.workshop)
    sanitized = sanitize_fiscal_payload(payload)
    remote_uuid = str(sanitized.get("uuid") or "").strip()
    if locked.nfse_item_id and locked.remote_uuid and remote_uuid and str(locked.remote_uuid).lower() != remote_uuid.lower():
        raise NfseManualEmissionError("O retorno pertence a outra NFS-e manual.")
    locked.response_payload = sanitized
    if remote_uuid:
        locked.remote_uuid = remote_uuid
    locked.verification_code = str(sanitized.get("codigo_verificacao") or locked.verification_code or "").strip()
    locked.xml_nfse = str(sanitized.get("xml") or locked.xml_nfse or "").strip()
    locked.danfse_pdf = str(sanitized.get("pdf_nfse") or sanitized.get("pdf") or locked.danfse_pdf or "").strip()
    if _is_success(sanitized):
        if str(sanitized.get("modelo") or "").strip().lower() != "nfse" or not remote_uuid:
            raise NfseManualEmissionError("A resposta aprovada nao possui modelo NFS-e e UUID validos.")
        response_rps_number = str(sanitized.get("numero_rps") or sanitized.get("rps_numero") or "").strip()
        response_rps_series = str(sanitized.get("serie_rps") or sanitized.get("rps_serie") or "").strip()
        if response_rps_number and response_rps_number != str(locked.rps_number):
            raise NfseManualEmissionError("A resposta aprovada referencia outro numero de RPS.")
        if response_rps_series and response_rps_series != locked.rps_series:
            raise NfseManualEmissionError("A resposta aprovada referencia outra serie de RPS.")
        if NfseItem.objects.filter(uuid=remote_uuid).exclude(pk=locked.nfse_item_id).exists():
            raise NfseManualEmissionError("UUID da NFS-e manual esta ambiguo no Hunter.")
        mapped = map_item_payload(sanitized)
        item, _created = NfseItem.objects.get_or_create(
            uuid=remote_uuid,
            defaults={"workshop": locked.workshop, "status": NfseItemStatus.aprovado},
        )
        if item.workshop_id != locked.workshop_id:
            raise NfseManualEmissionError("A NFS-e manual retornada pertence a outra oficina.")
        item.status = NfseItemStatus.aprovado
        item.model = str(mapped.get("model") or "nfse")
        item.reason = str(mapped.get("reason") or "")
        item.number = str(mapped.get("number") or item.number or "")
        item.verification_code = str(mapped.get("verification_code") or item.verification_code or "")
        item.rps_series = str(mapped.get("rps_series") or locked.rps_series)
        item.rps_number = str(mapped.get("rps_number") or locked.rps_number)
        item.xml_url = locked.xml_nfse
        item.pdf_nfse_url = locked.danfse_pdf
        item.pdf_rps_url = str(mapped.get("pdf_rps_url") or item.pdf_rps_url or "")
        item.raw_payload = sanitized
        item.last_update_source = update_source
        item.remote_updated_at = mapped.get("remote_updated_at")
        item.save(update_fields=["status", "model", "reason", "number", "verification_code", "rps_series", "rps_number", "xml_url", "pdf_nfse_url", "pdf_rps_url", "raw_payload", "last_update_source", "remote_updated_at"])
        locked.nfse_item = item
        locked.status = FiscalEmissionAttemptStatus.SUCCEEDED
        locked.is_uncertain = False
        locked.completed_at = timezone.now()
    elif _is_failure(sanitized):
        locked.status = FiscalEmissionAttemptStatus.FAILED
        locked.is_uncertain = False
        locked.completed_at = timezone.now()
    elif _is_processing(sanitized):
        locked.status = FiscalEmissionAttemptStatus.SENT
        locked.is_uncertain = False
    else:
        locked.status = FiscalEmissionAttemptStatus.UNCERTAIN
        locked.is_uncertain = True
    locked.save(update_fields=["response_payload", "remote_uuid", "verification_code", "xml_nfse", "danfse_pdf", "nfse_item", "status", "is_uncertain", "completed_at", "atualizado_em"])
    return locked


def emit_nfse_manual_from_preview(*, preview: NfseManualEmissionPreview, requested_by: Any | None = None) -> NfseManualEmission:
    emission, attempt, payload = _create_intention(preview=preview, created_by=requested_by)
    mark_attempt_sent(attempt=attempt)
    emission.status = FiscalEmissionAttemptStatus.SENT
    emission.sent_at = timezone.now()
    emission.save(update_fields=["status", "sent_at", "atualizado_em"])
    try:
        response = requests.post(_build_manual_emission_url(), json=payload, headers=_build_headers(workshop=preview.workshop), timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = "Timeout ao emitir NFS-e manual; estado remoto incerto. Consulte antes de qualquer nova tentativa."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_uncertain(emission=emission, message=message)
        raise NfseManualEmissionError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao emitir NFS-e manual", scope="nfse")
        mark_attempt_failed(attempt=attempt, error_message=message)
        emission.status = FiscalEmissionAttemptStatus.FAILED
        emission.response_payload = sanitize_fiscal_payload({"error": message})
        emission.completed_at = timezone.now()
        emission.save(update_fields=["status", "response_payload", "completed_at", "atualizado_em"])
        raise NfseManualEmissionError(message) from exc
    try:
        response_payload = response.json()
    except ValueError as exc:
        message = "Resposta invalida ao emitir NFS-e manual; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_uncertain(emission=emission, message=message)
        raise NfseManualEmissionError(message) from exc
    if not isinstance(response_payload, dict):
        message = "Resposta invalida ao emitir NFS-e manual; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_uncertain(emission=emission, message=message)
        raise NfseManualEmissionError(message)
    try:
        emission = apply_nfse_manual_emission_payload(emission=emission, payload=response_payload, update_source="manual_emission")
    except NfseManualEmissionError as exc:
        mark_attempt_uncertain(attempt=attempt, error_message=str(exc))
        _mark_uncertain(emission=emission, message=str(exc))
        raise
    if emission.status == FiscalEmissionAttemptStatus.FAILED:
        message = extract_webmania_error_message(response_payload, scope="nfse") or "Emissao manual NFS-e rejeitada."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        raise NfseManualEmissionError(message)
    if emission.status == FiscalEmissionAttemptStatus.SUCCEEDED:
        mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    else:
        attempt.response_payload = sanitize_fiscal_payload(response_payload)
        attempt.remote_uuid = str(response_payload.get("uuid") or "")
        attempt.save(update_fields=["response_payload", "remote_uuid", "atualizado_em"])
    return emission


def resolve_nfse_manual_emission_for_webhook(*, payload: dict[str, Any]) -> NfseManualEmission | None:
    event_uuid = str(payload.get("uuid") or "").strip()
    queryset = NfseManualEmission.objects.exclude(status=FiscalEmissionAttemptStatus.FAILED)
    if not event_uuid:
        direct = []
    else:
        direct = list(queryset.filter(remote_uuid=event_uuid).order_by("pk")[:2])
    if len(direct) == 1:
        return direct[0]
    if len(direct) > 1:
        return None
    rps_number = str(payload.get("numero_rps") or payload.get("rps_numero") or "").strip()
    rps_series = str(payload.get("serie_rps") or payload.get("rps_serie") or "").strip()
    if not rps_number.isdigit() or not rps_series:
        return None
    matches = list(queryset.filter(rps_number=int(rps_number), rps_series=rps_series, status__in=[FiscalEmissionAttemptStatus.SENT, FiscalEmissionAttemptStatus.UNCERTAIN]).order_by("pk")[:2])
    return matches[0] if len(matches) == 1 else None


def is_ambiguous_nfse_manual_emission_webhook(*, payload: dict[str, Any]) -> bool:
    event_uuid = str(payload.get("uuid") or "").strip()
    queryset = NfseManualEmission.objects.exclude(status=FiscalEmissionAttemptStatus.FAILED)
    if event_uuid and queryset.filter(remote_uuid=event_uuid).count() > 1:
        return True
    rps_number = str(payload.get("numero_rps") or payload.get("rps_numero") or "").strip()
    rps_series = str(payload.get("serie_rps") or payload.get("rps_serie") or "").strip()
    return bool(rps_number.isdigit() and rps_series and queryset.filter(rps_number=int(rps_number), rps_series=rps_series, status__in=[FiscalEmissionAttemptStatus.SENT, FiscalEmissionAttemptStatus.UNCERTAIN]).count() > 1)


def confirm_nfse_manual_emission_from_payload(*, emission: NfseManualEmission, payload: dict[str, Any], update_source: str) -> NfseManualEmission:
    applied = apply_nfse_manual_emission_payload(emission=emission, payload=payload, update_source=update_source)
    attempt = _attempt_for(applied)
    if attempt is not None:
        if applied.status == FiscalEmissionAttemptStatus.SUCCEEDED and attempt.status != FiscalEmissionAttemptStatus.SUCCEEDED:
            mark_attempt_succeeded(attempt=attempt, response_payload=payload)
        elif applied.status == FiscalEmissionAttemptStatus.FAILED and attempt.status != FiscalEmissionAttemptStatus.FAILED:
            mark_attempt_failed(attempt=attempt, error_message=extract_webmania_error_message(payload, scope="nfse") or "Emissao manual NFS-e rejeitada.", response_payload=payload)
    return applied


def reconcile_nfse_manual_emission(*, emission: NfseManualEmission) -> NfseManualEmission:
    if emission.status == FiscalEmissionAttemptStatus.SUCCEEDED:
        return emission
    if not emission.remote_uuid:
        raise NfseManualEmissionError("Emissao manual incerta sem UUID remoto exige decisao administrativa; nenhum POST sera repetido.")
    try:
        payload = consult_nfse_uuid(workshop=emission.workshop, event_uuid=str(emission.remote_uuid))
    except NfseConsultaError as exc:
        raise NfseManualEmissionError(str(exc)) from exc
    return confirm_nfse_manual_emission_from_payload(emission=emission, payload=payload, update_source="query")
