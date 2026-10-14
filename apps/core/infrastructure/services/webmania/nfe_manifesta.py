from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings

from apps.core.infrastructure.services.webmania.webmania_auth import (
    WebmaniaAuthError,
    build_webmania_headers,
    sanitize_webmania_setting,
    should_use_global_webmania_auth,
)
from apps.core.infrastructure.services.webmania.webmania_errors import (
    build_webmania_request_exception_message,
    extract_webmania_error_message,
)

MDE_EVENT_CONFIRMATION = "210200"
MDE_EVENT_ACKNOWLEDGEMENT = "210210"
MDE_EVENT_UNKNOWN = "210220"
MDE_EVENT_NOT_PERFORMED = "210240"

MDE_EVENTS_REQUIRING_JUSTIFICATION = frozenset({MDE_EVENT_NOT_PERFORMED})
ALLOWED_MDE_EVENTS = frozenset(
    {
        MDE_EVENT_CONFIRMATION,
        MDE_EVENT_ACKNOWLEDGEMENT,
        MDE_EVENT_UNKNOWN,
        MDE_EVENT_NOT_PERFORMED,
    }
)


class NfeManifestationError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class NfeManifestationResult:
    uuid: str
    status: str
    event_code: str
    xml_url: str
    raw_payload: dict[str, Any]


def _build_headers(*, workshop) -> dict[str, str]:
    try:
        if should_use_global_webmania_auth():
            return build_webmania_headers()
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfeManifestationError(str(exc)) from exc


def _build_manifesta_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFE_MANIFESTA_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"

    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/manifesta/"


def _normalize_access_key(access_key: str) -> str:
    normalized = "".join(character for character in str(access_key or "").strip() if character.isdigit())
    if len(normalized) != 44:
        raise NfeManifestationError("Informe uma chave de acesso da NF-e com 44 dígitos.")
    return normalized


def _normalize_event_code(event_code: str) -> str:
    normalized = str(event_code or "").strip()
    if normalized not in ALLOWED_MDE_EVENTS:
        raise NfeManifestationError("Evento de manifestação inválido.")
    return normalized


def build_manifesta_payload(
    *,
    access_key: str,
    event_code: str,
    justificativa: str = "",
    ambiente: int | None = None,
) -> dict[str, Any]:
    chave = _normalize_access_key(access_key)
    evento = _normalize_event_code(event_code)
    justification = str(justificativa or "").strip()

    if evento in MDE_EVENTS_REQUIRING_JUSTIFICATION and len(justification) < 15:
        raise NfeManifestationError("A operação não realizada exige justificativa com pelo menos 15 caracteres.")

    ambient = ambiente if ambiente is not None else int(getattr(settings, "WEBMANIA_AMBIENT", "2") or 2)
    return {
        "chave": chave,
        "ambiente": ambient,
        "evento": evento,
        "justificativa": justification if evento in MDE_EVENTS_REQUIRING_JUSTIFICATION else "",
    }


def manifesta_nfe(
    *,
    workshop,
    access_key: str,
    event_code: str,
    justificativa: str = "",
) -> NfeManifestationResult:
    headers = _build_headers(workshop=workshop)
    payload = build_manifesta_payload(
        access_key=access_key,
        event_code=event_code,
        justificativa=justificativa,
    )

    try:
        response = requests.post(_build_manifesta_url(), json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(
            exc,
            default="Falha ao enviar manifestação do destinatário",
            scope="nfe",
        )
        raise NfeManifestationError(message) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise NfeManifestationError("Resposta inválida da API de manifestação do destinatário.") from exc

    if not isinstance(data, dict):
        raise NfeManifestationError("Resposta inválida da API de manifestação do destinatário.")

    error_message = extract_webmania_error_message(
        data.get("error") or data.get("msg") or data.get("message"),
        scope="nfe",
    )
    if error_message:
        raise NfeManifestationError(error_message)

    status = str(data.get("status") or "").strip().lower()
    if status in {"reprovado", "rejeitado", "erro", "failed", "error"}:
        raise NfeManifestationError(
            extract_webmania_error_message(data, scope="nfe") or "Manifestação rejeitada pela SEFAZ."
        )

    return NfeManifestationResult(
        uuid=str(data.get("uuid") or "").strip(),
        status=status or "aprovado",
        event_code=str(data.get("evento") or payload["evento"]).strip(),
        xml_url=str(data.get("xml") or "").strip(),
        raw_payload=data,
    )
