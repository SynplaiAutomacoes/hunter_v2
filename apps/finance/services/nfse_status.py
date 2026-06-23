from __future__ import annotations

from typing import Any

import requests
from django.conf import settings
from django.utils import timezone

from apps.finance.models.finance import NfseMunicipalCapability
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting
from apps.finance.services.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


class NfseStatusError(Exception):
    pass


def _build_status_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFSE_STATUS_ENDPOINT", ""))
    if custom_endpoint:
        return custom_endpoint
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_BASE_URL", "https://api.webmania.com.br/2/")).rstrip("/")
    return f"{base_url}/nfse/status"


def _build_headers(*, workshop: Any) -> dict[str, str]:
    try:
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfseStatusError(str(exc)) from exc


def consult_nfse_municipal_status(*, capability: NfseMunicipalCapability) -> dict[str, Any]:
    try:
        response = requests.get(_build_status_url(), headers=_build_headers(workshop=capability.workshop), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao consultar status municipal NFS-e", scope="nfse")
        capability.last_status_error = message
        capability.save(update_fields=["last_status_error", "atualizado_em"])
        raise NfseStatusError(message) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        message = "Resposta invalida da API de status municipal NFS-e."
        capability.last_status_error = message
        capability.save(update_fields=["last_status_error", "atualizado_em"])
        raise NfseStatusError(message) from exc

    if not isinstance(payload, dict):
        message = "Resposta invalida da API de status municipal NFS-e."
        capability.last_status_error = message
        capability.save(update_fields=["last_status_error", "atualizado_em"])
        raise NfseStatusError(message)

    sanitized_payload = sanitize_fiscal_payload(payload)
    error_message = extract_webmania_error_message(sanitized_payload.get("error") or sanitized_payload.get("msg") or sanitized_payload.get("message"), scope="nfse")
    if error_message:
        capability.last_status_error = error_message
        capability.save(update_fields=["last_status_error", "atualizado_em"])
        raise NfseStatusError(error_message)

    remote_status = sanitized_payload.get("status")
    capability.remote_status = remote_status if isinstance(remote_status, bool) else None
    capability.remote_payload = sanitized_payload
    capability.last_synced_at = timezone.now()
    capability.last_status_error = ""
    capability.save(update_fields=["remote_status", "remote_payload", "last_synced_at", "last_status_error", "atualizado_em"])
    return sanitized_payload
