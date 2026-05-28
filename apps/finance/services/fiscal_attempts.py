from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.finance.models.finance import FiscalEmissionAttempt, FiscalEmissionAttemptStatus


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
    return value


def build_fiscal_idempotency_key(*, document_kind: str, request_id: int) -> str:
    return f"{document_kind}:request:{request_id}"


def _blocked_message(attempt: FiscalEmissionAttempt) -> str:
    if attempt.status == FiscalEmissionAttemptStatus.UNCERTAIN:
        return "Ja existe uma tentativa fiscal em estado incerto para esta emissao. Consulte ou reconcilie o documento remoto antes de tentar novamente."
    if attempt.status == FiscalEmissionAttemptStatus.SUCCEEDED:
        return "Esta emissao fiscal ja possui uma tentativa remota concluida."
    return "Ja existe uma tentativa fiscal remota registrada para esta emissao."


def begin_emission_attempt(*, workshop: Any, document_kind: str, request_model: str, request_id: int, request_payload: dict[str, Any]) -> FiscalEmissionAttempt:
    idempotency_key = build_fiscal_idempotency_key(document_kind=document_kind, request_id=request_id)
    sanitized_payload = sanitize_fiscal_payload(request_payload)

    try:
        with transaction.atomic():
            attempt, created = FiscalEmissionAttempt.objects.select_for_update().get_or_create(
                workshop=workshop,
                document_kind=document_kind,
                idempotency_key=idempotency_key,
                defaults={
                    "request_model": request_model,
                    "request_id": request_id,
                    "request_payload": sanitized_payload,
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
