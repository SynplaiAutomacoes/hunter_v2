from __future__ import annotations

from typing import Any

import requests
from django.conf import settings
from django.utils import timezone

from apps.finance.models.finance import NfeItem
from apps.core.infrastructure.services.webmania.nfe_emission import apply_nfe_item_payload
from apps.core.infrastructure.services.webmania.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


class NfeConsultaError(Exception):
    pass


def _build_headers(*, workshop=None) -> dict[str, str]:
    try:
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfeConsultaError(str(exc)) from exc


def _build_consulta_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_CONSULTA_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"

    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/consulta/"


def consult_nfe_item(*, item: NfeItem) -> dict[str, Any]:
    params: dict[str, str] = {}
    if str(item.uuid or "").strip():
        params["uuid"] = str(item.uuid)
    elif str(item.access_key or "").strip():
        params["chave"] = str(item.access_key).strip()
    else:
        raise NfeConsultaError("Nao foi possivel consultar a Nota Fiscal sem UUID ou chave de acesso.")

    try:
        response = requests.get(
            _build_consulta_url(),
            params=params,
            headers=_build_headers(workshop=item.workshop),
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao consultar status da Nota Fiscal", scope="nfe")
        raise NfeConsultaError(message) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise NfeConsultaError("Resposta invalida da API de consulta da Nota Fiscal.") from exc

    if not isinstance(payload, dict):
        raise NfeConsultaError("Resposta invalida da API de consulta da Nota Fiscal.")

    error_message = extract_webmania_error_message(payload.get("error") or payload.get("msg") or payload.get("message"), scope="nfe")
    if error_message:
        raise NfeConsultaError(error_message)

    return payload


def reconcile_nfe_item(*, item: NfeItem) -> NfeItem:
    try:
        payload = consult_nfe_item(item=item)
        apply_nfe_item_payload(item=item, response_payload=payload, reconciled_at=timezone.now())
        item.refresh_from_db()
        return item
    except NfeConsultaError as exc:
        item.last_sync_error = str(exc)
        item.save(update_fields=["last_sync_error"])
        raise
