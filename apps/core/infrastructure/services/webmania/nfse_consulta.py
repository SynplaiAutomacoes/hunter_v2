from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings
from django.utils import timezone

from apps.core.observability import observe_dependency_call
from apps.finance.models.finance import NfseItem
from apps.core.infrastructure.services.webmania.emission import apply_nfse_item_payload
from apps.core.infrastructure.services.webmania.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


logger = logging.getLogger(__name__)


class NfseConsultaError(Exception):
    pass


def _build_headers(*, workshop=None) -> dict[str, str]:
    try:
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfseConsultaError(str(exc)) from exc


def _build_consulta_url(*, event_uuid: str) -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFSE_CONSULTA_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/{event_uuid}"

    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_BASE_URL", "https://api.webmania.com.br/2/")).rstrip("/")
    return f"{base_url}/nfse/consulta/{event_uuid}"


def consult_nfse_item(*, item: NfseItem) -> dict[str, Any]:
    event_uuid = str(item.uuid or "").strip()
    if not event_uuid:
        raise NfseConsultaError("Nao foi possivel consultar a Nota Fiscal de Serviço sem UUID.")

    try:
        with observe_dependency_call(
            logger=logger,
            dependency_type="http",
            dependency_name="webmania",
            operation="consult_nfse_item",
            log_context={"event_uuid": event_uuid, "workshop_id": getattr(item.workshop, "pk", None)},
        ) as dependency_call:
            response = requests.get(
                _build_consulta_url(event_uuid=event_uuid),
                headers=_build_headers(workshop=item.workshop),
                timeout=30,
            )
            dependency_call.set_http_status_code(response.status_code)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise NfseConsultaError("Resposta invalida da API de consulta da Nota Fiscal de Serviço.")

            error_message = extract_webmania_error_message(payload.get("error") or payload.get("msg") or payload.get("message"), scope="nfse")
            if error_message:
                raise NfseConsultaError(error_message)

            dependency_call.set_attribute("app.payload_type", type(payload).__name__)
            dependency_call.success(extra={"status": str(payload.get("status") or "")})
            return payload
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao consultar status da Nota Fiscal de Serviço", scope="nfse")
        raise NfseConsultaError(message) from exc
    except ValueError as exc:
        raise NfseConsultaError("Resposta invalida da API de consulta da Nota Fiscal de Serviço.") from exc


def reconcile_nfse_item(*, item: NfseItem) -> NfseItem:
    try:
        payload = consult_nfse_item(item=item)
        apply_nfse_item_payload(item=item, response_payload=payload, reconciled_at=timezone.now())
        item.refresh_from_db()
        return item
    except NfseConsultaError as exc:
        item.last_sync_error = str(exc)
        item.save(update_fields=["last_sync_error"])
        raise
