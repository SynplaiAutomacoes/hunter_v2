from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.finance.models.finance import FiscalDocument, FiscalDocumentEvent, FiscalEmissionAttempt, FiscalEmissionAttemptStatus, FiscalEmissionOperationType, FiscalNumberInutilization


SENSITIVE_PAYLOAD_KEYS = {
    "access_token",
    "access_token_secret",
    "authorization",
    "bearer",
    "certificado",
    "consumer_key",
    "consumer_secret",
    "password",
    "senha",
    "token",
}

_SENSITIVE_QUERY_PATTERN = re.compile(r"([?&](?:token|access_token|authorization)=)[^&]+", flags=re.IGNORECASE)


class FiscalEmissionAttemptBlocked(Exception):
    pass


def sanitize_fiscal_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, nested_value in value.items():
            normalized_key = str(key).strip().lower()
            if normalized_key in SENSITIVE_PAYLOAD_KEYS or any(secret_fragment in normalized_key for secret_fragment in ("secret", "senha", "token", "certificado", "authorization")):
                sanitized[str(key)] = "[REDACTED]"
                continue
            sanitized[str(key)] = sanitize_fiscal_payload(nested_value)
        return sanitized
    if isinstance(value, list):
        return [sanitize_fiscal_payload(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_fiscal_payload(item) for item in value]
    if isinstance(value, str):
        return _SENSITIVE_QUERY_PATTERN.sub(r"\1[REDACTED]", value)
    return value


def build_fiscal_idempotency_key(*, document_kind: str, request_id: int) -> str:
    return f"{document_kind}:request:{request_id}"


def build_fiscal_operation_idempotency_key(*, workshop_id: int, document_id: int, operation_type: str, sequence: int) -> str:
    raw_value = f"{workshop_id}:{document_id}:{operation_type}:{sequence}"
    digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()
    return f"{operation_type}:{digest}"


def build_fiscal_document_operation_idempotency_key(*, workshop_id: int, derived_document_id: int, operation_type: str, request_generation: int = 1) -> str:
    raw_value = f"{workshop_id}:{derived_document_id}:{operation_type}:{request_generation}"
    digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()
    return f"{operation_type}:{digest}"


def build_payload_hash(payload: dict[str, Any]) -> str:
    canonical_payload = json.dumps(sanitize_fiscal_payload(payload), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def _blocked_message(attempt: FiscalEmissionAttempt) -> str:
    if attempt.status == FiscalEmissionAttemptStatus.UNCERTAIN:
        return "Já existe uma tentativa fiscal em estado incerto para esta emissão. Consulte ou reconcilie o documento remoto antes de tentar novamente."
    if attempt.status == FiscalEmissionAttemptStatus.SUCCEEDED:
        return "Esta emissão fiscal já possui uma tentativa remota concluída."
    return "Já existe uma tentativa fiscal remota registrada para esta emissão."


def begin_emission_attempt(
    *,
    workshop: Any,
    document_kind: str,
    request_model: str,
    request_id: int,
    request_payload: dict[str, Any],
    idempotency_key: str | None = None,
    operation_type: str = FiscalEmissionOperationType.EMISSION,
    fiscal_document: FiscalDocument | None = None,
    fiscal_document_event: FiscalDocumentEvent | None = None,
    fiscal_number_inutilization: FiscalNumberInutilization | None = None,
    payload_hash: str = "",
) -> FiscalEmissionAttempt:
    idempotency_key = idempotency_key or build_fiscal_idempotency_key(document_kind=document_kind, request_id=request_id)
    sanitized_payload = sanitize_fiscal_payload(request_payload)
    payload_hash = payload_hash or build_payload_hash(sanitized_payload)

    try:
        with transaction.atomic():
            attempt, created = FiscalEmissionAttempt.objects.select_for_update().get_or_create(
                workshop=workshop,
                document_kind=document_kind,
                idempotency_key=idempotency_key,
                defaults={
                    "request_model": request_model,
                    "request_id": request_id,
                    "operation_type": operation_type,
                    "fiscal_document": fiscal_document,
                    "fiscal_document_event": fiscal_document_event,
                    "fiscal_number_inutilization": fiscal_number_inutilization,
                    "request_payload": sanitized_payload,
                    "payload_hash": payload_hash,
                    "status": FiscalEmissionAttemptStatus.STARTED,
                },
            )
            if not created:
                raise FiscalEmissionAttemptBlocked(_blocked_message(attempt))
            return attempt
    except IntegrityError as exc:
        attempt = FiscalEmissionAttempt.objects.filter(workshop=workshop, document_kind=document_kind, idempotency_key=idempotency_key).first()
        if attempt is not None:
            raise FiscalEmissionAttemptBlocked(_blocked_message(attempt)) from exc
        raise


def mark_attempt_sent(*, attempt: FiscalEmissionAttempt) -> None:
    attempt.status = FiscalEmissionAttemptStatus.SENT
    attempt.sent_at = timezone.now()
    attempt.error_message = ""
    attempt.save(update_fields=["status", "sent_at", "error_message", "atualizado_em"])


def mark_attempt_succeeded(*, attempt: FiscalEmissionAttempt, response_payload: dict[str, Any]) -> None:
    attempt.status = FiscalEmissionAttemptStatus.SUCCEEDED
    attempt.completed_at = timezone.now()
    attempt.response_payload = sanitize_fiscal_payload(response_payload)
    attempt.error_message = ""
    attempt.remote_model = str(response_payload.get("modelo") or response_payload.get("model") or "").strip().lower()
    attempt.remote_uuid = str(response_payload.get("uuid") or "").strip()
    attempt.remote_key = str(response_payload.get("chave") or "").strip()
    attempt.save(update_fields=["status", "completed_at", "response_payload", "error_message", "remote_model", "remote_uuid", "remote_key", "atualizado_em"])


def mark_attempt_failed(*, attempt: FiscalEmissionAttempt, error_message: str, response_payload: dict[str, Any] | None = None) -> None:
    attempt.status = FiscalEmissionAttemptStatus.FAILED
    attempt.completed_at = timezone.now()
    attempt.error_message = str(error_message or "").strip()
    if response_payload is not None:
        attempt.response_payload = sanitize_fiscal_payload(response_payload)
        attempt.remote_model = str(response_payload.get("modelo") or response_payload.get("model") or "").strip().lower()
        attempt.remote_uuid = str(response_payload.get("uuid") or "").strip()
        attempt.remote_key = str(response_payload.get("chave") or "").strip()
    attempt.save(update_fields=["status", "completed_at", "error_message", "response_payload", "remote_model", "remote_uuid", "remote_key", "atualizado_em"])


def mark_attempt_uncertain(*, attempt: FiscalEmissionAttempt, error_message: str) -> None:
    attempt.status = FiscalEmissionAttemptStatus.UNCERTAIN
    attempt.error_message = str(error_message or "").strip()
    attempt.save(update_fields=["status", "error_message", "atualizado_em"])
