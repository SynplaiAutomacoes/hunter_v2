from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.finance.models.finance import FiscalDocument, FiscalDocumentStatus, FiscalDocumentType, FiscalEmissionAttemptStatus, FiscalEmissionDocumentKind, FiscalEmissionOperationType, FiscalNumberInutilization, FiscalNumberInutilizationStatus, WebmaniaCompany
from apps.finance.services.fiscal_attempts import FiscalEmissionAttemptBlocked, begin_emission_attempt, build_payload_hash, mark_attempt_failed, mark_attempt_sent, mark_attempt_succeeded, mark_attempt_uncertain, sanitize_fiscal_payload
from apps.finance.services.nfce_emission import NfceEmissionError, _build_headers, validate_nfce_configuration
from apps.core.infrastructure.services.webmania.webmania_auth import sanitize_webmania_setting
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


logger = logging.getLogger(__name__)

NFCE_INUTILIZATION_MIN_REASON_LENGTH = 15
NFCE_INUTILIZATION_MAX_REASON_LENGTH = 255

_SEQUENCE_PATTERN = re.compile(r"^\s*(?P<start>\d+)(?:\s*-\s*(?P<end>\d+))?\s*$")


class NfceInutilizationError(NfceEmissionError):
    pass


def _build_inutilization_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFCE_INUTILIZATION_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/inutilizar/"


def validate_nfce_inutilization_reason(reason: str) -> str:
    normalized = str(reason or "").strip()
    if len(normalized) < NFCE_INUTILIZATION_MIN_REASON_LENGTH or len(normalized) > NFCE_INUTILIZATION_MAX_REASON_LENGTH:
        raise NfceInutilizationError("Informe um motivo de inutilizacao entre 15 e 255 caracteres.")
    return normalized


def normalize_nfce_inutilization_range(*, sequence_start: Any, sequence_end: Any | None = None) -> tuple[int, int]:
    if sequence_end is None and isinstance(sequence_start, str):
        match = _SEQUENCE_PATTERN.match(sequence_start)
        if match is None:
            raise NfceInutilizationError("Informe sequencia numerica ou intervalo no formato inicial-final.")
        start = int(match.group("start"))
        end = int(match.group("end") or match.group("start"))
    else:
        try:
            start = int(sequence_start)
            end = int(sequence_end if sequence_end not in (None, "") else sequence_start)
        except (TypeError, ValueError) as exc:
            raise NfceInutilizationError("Informe sequencia inicial e final validas.") from exc
    if start <= 0 or end <= 0:
        raise NfceInutilizationError("A sequencia da NFC-e deve ser maior que zero.")
    if start > end:
        raise NfceInutilizationError("A sequencia inicial nao pode ser maior que a final.")
    return start, end


def format_nfce_inutilization_sequence(*, sequence_start: int, sequence_end: int) -> str:
    return str(sequence_start) if sequence_start == sequence_end else f"{sequence_start}-{sequence_end}"


def _active_inutilization_statuses() -> set[str]:
    return {
        FiscalNumberInutilizationStatus.STARTED,
        FiscalNumberInutilizationStatus.SENT,
        FiscalNumberInutilizationStatus.SUCCEEDED,
        FiscalNumberInutilizationStatus.UNCERTAIN,
    }


def _blocking_nfce_document_statuses() -> set[str]:
    return {
        FiscalDocumentStatus.PROCESSING,
        FiscalDocumentStatus.APPROVED,
        FiscalDocumentStatus.CANCELED,
        FiscalDocumentStatus.DENIED,
        FiscalDocumentStatus.CONTINGENCY,
        FiscalDocumentStatus.UNCERTAIN,
    }


def validate_nfce_inutilization_configuration(*, workshop: Any, environment: int, series: Any) -> WebmaniaCompany:
    if int(environment) not in {1, 2}:
        raise NfceInutilizationError("Ambiente da inutilizacao NFC-e invalido.")
    try:
        company = validate_nfce_configuration(workshop=workshop, environment=int(environment))
    except NfceEmissionError as exc:
        raise NfceInutilizationError(str(exc)) from exc
    normalized_series = str(series or "").strip()
    if not normalized_series.isdigit():
        raise NfceInutilizationError("Informe serie NFC-e valida.")
    company_series = str(company.nfce_serie or "").strip()
    if normalized_series != company_series:
        raise NfceInutilizationError("A serie informada nao corresponde a serie NFC-e configurada para a oficina.")
    return company


def _assert_no_local_nfce_in_range(*, workshop: Any, environment: int, series: str, sequence_start: int, sequence_end: int) -> None:
    candidates = FiscalDocument.objects.filter(
        workshop=workshop,
        document_type=FiscalDocumentType.NFCE,
        environment=str(int(environment)),
        series=str(series),
        status__in=_blocking_nfce_document_statuses(),
    ).exclude(number="")
    for document in candidates:
        number = str(document.number or "").strip()
        if number.isdigit() and sequence_start <= int(number) <= sequence_end:
            raise NfceInutilizationError("A faixa contem NFC-e conhecida localmente e nao pode ser inutilizada.")


def _assert_no_overlapping_inutilization(*, workshop: Any, environment: int, series: str, sequence_start: int, sequence_end: int, exclude_pk: int | None = None) -> None:
    queryset = FiscalNumberInutilization.objects.filter(
        workshop=workshop,
        document_type=FiscalDocumentType.NFCE,
        environment=str(int(environment)),
        series=str(series),
        status__in=_active_inutilization_statuses(),
        sequence_start__lte=sequence_end,
        sequence_end__gte=sequence_start,
    )
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    if queryset.exists():
        raise NfceInutilizationError("Ja existe inutilizacao ativa, concluida ou incerta sobrepondo esta faixa.")


def assert_nfce_inutilization_range_available(*, workshop: Any, environment: int, series: str, sequence_start: int, sequence_end: int, exclude_pk: int | None = None) -> None:
    _assert_no_overlapping_inutilization(workshop=workshop, environment=environment, series=series, sequence_start=sequence_start, sequence_end=sequence_end, exclude_pk=exclude_pk)
    _assert_no_local_nfce_in_range(workshop=workshop, environment=environment, series=series, sequence_start=sequence_start, sequence_end=sequence_end)


def build_nfce_inutilization_payload(*, sequence_start: int, sequence_end: int, reason: str, environment: int, series: str) -> dict[str, str]:
    return {
        "sequencia": format_nfce_inutilization_sequence(sequence_start=sequence_start, sequence_end=sequence_end),
        "motivo": reason,
        "ambiente": str(int(environment)),
        "serie": str(series),
        "modelo": "2",
    }


def _build_nfce_inutilization_idempotency_key(*, workshop_id: int, inutilization_id: int, request_generation: int = 1) -> str:
    raw_value = f"{workshop_id}:{inutilization_id}:{FiscalEmissionOperationType.NFCE_INUTILIZATION}:{request_generation}"
    digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()
    return f"{FiscalEmissionOperationType.NFCE_INUTILIZATION}:{digest}"


def create_nfce_inutilization_draft(
    *,
    workshop: Any,
    requested_by: Any | None,
    environment: int,
    series: Any,
    sequence_start: Any,
    sequence_end: Any | None,
    reason: str,
    local_limitation_confirmation: bool = False,
) -> FiscalNumberInutilization:
    if not local_limitation_confirmation:
        raise NfceInutilizationError("Confirme que a verificacao local nao garante ausencia de uso fora do Hunter.")
    reason = validate_nfce_inutilization_reason(reason)
    start, end = normalize_nfce_inutilization_range(sequence_start=sequence_start, sequence_end=sequence_end)
    with transaction.atomic():
        company = WebmaniaCompany.objects.select_for_update().filter(workshop=workshop).first()
        if company is None:
            raise NfceInutilizationError("Configure a empresa emissora da oficina antes de inutilizar numeracao NFC-e.")
        validate_nfce_inutilization_configuration(workshop=workshop, environment=int(environment), series=series)
        normalized_series = str(series or "").strip()
        assert_nfce_inutilization_range_available(workshop=workshop, environment=int(environment), series=normalized_series, sequence_start=start, sequence_end=end)
        payload = build_nfce_inutilization_payload(sequence_start=start, sequence_end=end, reason=reason, environment=int(environment), series=normalized_series)
        return FiscalNumberInutilization.objects.create(
            workshop=workshop,
            account=getattr(workshop, "account", None),
            document_type=FiscalDocumentType.NFCE,
            environment=str(int(environment)),
            series=normalized_series,
            sequence_start=start,
            sequence_end=end,
            reason=reason,
            status=FiscalNumberInutilizationStatus.STARTED,
            remote_status=FiscalEmissionAttemptStatus.STARTED,
            request_payload=sanitize_fiscal_payload(payload),
            requested_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
            requested_at=timezone.now(),
        )


def _is_failed_inutilization_response(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or payload.get("remote_status") or "").strip().lower()
    if status in {"erro", "error", "falha", "failed", "reprovado", "rejeitado"}:
        return True
    return bool(extract_webmania_error_message(payload.get("error") or payload.get("erro") or payload.get("message") or payload.get("mensagem"), scope="nfe"))


def _is_successful_inutilization_response(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or payload.get("remote_status") or "").strip().lower()
    if _is_failed_inutilization_response(payload):
        return False
    return status in {"sucesso", "success", "succeeded", "inutilizado", "inutilizada", "aprovado", "autorizado"}


def apply_nfce_inutilization_payload(*, inutilization: FiscalNumberInutilization, response_payload: dict[str, Any]) -> FiscalNumberInutilization:
    sanitized_payload = sanitize_fiscal_payload(response_payload)
    inutilization.response_payload = sanitized_payload
    inutilization.remote_status = str(response_payload.get("status") or response_payload.get("remote_status") or inutilization.remote_status or "").strip()
    inutilization.remote_uuid = str(response_payload.get("uuid") or response_payload.get("remote_uuid") or inutilization.remote_uuid or "").strip()
    inutilization.protocol = str(response_payload.get("protocolo") or response_payload.get("protocol") or response_payload.get("recibo") or inutilization.protocol or "").strip()
    inutilization.xml_url = str(response_payload.get("xml") or response_payload.get("xml_inutilizacao") or inutilization.xml_url or "").strip()
    if _is_successful_inutilization_response(response_payload):
        inutilization.status = FiscalNumberInutilizationStatus.SUCCEEDED
        inutilization.completed_at = timezone.now()
    elif _is_failed_inutilization_response(response_payload):
        inutilization.status = FiscalNumberInutilizationStatus.FAILED
        inutilization.completed_at = timezone.now()
    else:
        inutilization.status = FiscalNumberInutilizationStatus.SENT
    inutilization.save(update_fields=["response_payload", "remote_status", "remote_uuid", "protocol", "xml_url", "status", "completed_at", "atualizado_em"])
    return inutilization


def _mark_inutilization_uncertain(*, inutilization: FiscalNumberInutilization, error_message: str) -> None:
    inutilization.status = FiscalNumberInutilizationStatus.UNCERTAIN
    inutilization.remote_status = FiscalNumberInutilizationStatus.UNCERTAIN
    inutilization.response_payload = sanitize_fiscal_payload({"error": error_message})
    inutilization.save(update_fields=["status", "remote_status", "response_payload", "atualizado_em"])


def _assert_transmittable(*, inutilization: FiscalNumberInutilization) -> None:
    existing_attempt = inutilization.emission_attempts.filter(operation_type=FiscalEmissionOperationType.NFCE_INUTILIZATION).order_by("-pk").first()
    if existing_attempt is None:
        return
    if existing_attempt.status == FiscalEmissionAttemptStatus.UNCERTAIN:
        raise NfceInutilizationError("Ja existe tentativa de inutilizacao NFC-e em estado remoto incerto. Nao reenvie automaticamente.")
    if existing_attempt.status in {FiscalEmissionAttemptStatus.SENT, FiscalEmissionAttemptStatus.SUCCEEDED}:
        raise NfceInutilizationError("Esta intencao de inutilizacao NFC-e ja possui envio remoto registrado.")
    raise NfceInutilizationError("Esta intencao de inutilizacao NFC-e ja possui tentativa fiscal registrada.")


def transmit_nfce_inutilization(*, inutilization: FiscalNumberInutilization) -> FiscalNumberInutilization:
    with transaction.atomic():
        locked = FiscalNumberInutilization.objects.select_for_update().select_related("workshop").get(pk=inutilization.pk)
        _assert_transmittable(inutilization=locked)
        validate_nfce_inutilization_configuration(workshop=locked.workshop, environment=int(locked.environment), series=locked.series)
        assert_nfce_inutilization_range_available(workshop=locked.workshop, environment=int(locked.environment), series=locked.series, sequence_start=locked.sequence_start, sequence_end=locked.sequence_end, exclude_pk=locked.pk)
        payload = dict(locked.request_payload or {})
        try:
            attempt = begin_emission_attempt(
                workshop=locked.workshop,
                document_kind=FiscalEmissionDocumentKind.NFCE,
                operation_type=FiscalEmissionOperationType.NFCE_INUTILIZATION,
                request_model=FiscalNumberInutilization.__name__,
                request_id=locked.pk,
                fiscal_number_inutilization=locked,
                idempotency_key=_build_nfce_inutilization_idempotency_key(workshop_id=locked.workshop_id, inutilization_id=locked.pk),
                request_payload=payload,
                payload_hash=build_payload_hash(payload),
            )
        except FiscalEmissionAttemptBlocked as exc:
            raise NfceInutilizationError(str(exc)) from exc

    headers = _build_headers(workshop=locked.workshop)
    mark_attempt_sent(attempt=attempt)
    locked.status = FiscalNumberInutilizationStatus.SENT
    locked.save(update_fields=["status", "atualizado_em"])
    try:
        response = requests.put(_build_inutilization_url(), json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.Timeout as exc:
        message = "Timeout ao inutilizar numeracao NFC-e; faixa em estado remoto incerto."
        logger.warning("nfce_inutilization_timeout", extra={"fiscal_number_inutilization_id": locked.pk, "fiscal_attempt_id": attempt.pk})
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_inutilization_uncertain(inutilization=locked, error_message=message)
        raise NfceInutilizationError(message) from exc
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao inutilizar numeracao NFC-e", scope="nfe")
        mark_attempt_failed(attempt=attempt, error_message=message)
        locked.status = FiscalNumberInutilizationStatus.FAILED
        locked.remote_status = FiscalNumberInutilizationStatus.FAILED
        locked.response_payload = sanitize_fiscal_payload({"error": message})
        locked.completed_at = timezone.now()
        locked.save(update_fields=["status", "remote_status", "response_payload", "completed_at", "atualizado_em"])
        raise NfceInutilizationError(message) from exc

    try:
        response_payload = response.json()
    except ValueError as exc:
        message = "Resposta invalida ao inutilizar numeracao NFC-e; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_inutilization_uncertain(inutilization=locked, error_message=message)
        raise NfceInutilizationError(message) from exc
    if not isinstance(response_payload, dict):
        message = "Resposta invalida ao inutilizar numeracao NFC-e; estado remoto incerto."
        mark_attempt_uncertain(attempt=attempt, error_message=message)
        _mark_inutilization_uncertain(inutilization=locked, error_message=message)
        raise NfceInutilizationError(message)

    locked = apply_nfce_inutilization_payload(inutilization=locked, response_payload=response_payload)
    if _is_failed_inutilization_response(response_payload):
        message = extract_webmania_error_message(response_payload, scope="nfe") or "Inutilizacao NFC-e rejeitada."
        mark_attempt_failed(attempt=attempt, error_message=message, response_payload=response_payload)
        raise NfceInutilizationError(message)
    if locked.status == FiscalNumberInutilizationStatus.SUCCEEDED:
        mark_attempt_succeeded(attempt=attempt, response_payload=response_payload)
    return locked


def create_and_transmit_nfce_inutilization(**kwargs: Any) -> FiscalNumberInutilization:
    inutilization = create_nfce_inutilization_draft(**kwargs)
    return transmit_nfce_inutilization(inutilization=inutilization)
