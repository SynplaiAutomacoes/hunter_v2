from __future__ import annotations

from typing import Any

import requests
from django.conf import settings

from apps.finance.services.webmania_auth import WebmaniaAuthError, build_webmania_headers, sanitize_webmania_setting


class TaxClassServiceError(Exception):
    pass


def _is_debug_enabled() -> bool:
    return bool(getattr(settings, "TAX_CLASS_DEBUG_LOGS", True))


def _debug_print(message: str, payload: Any | None = None) -> None:
    if not _is_debug_enabled():
        return

    prefix = "[TAX CLASS POST DEBUG]"
    if payload is None:
        print(f"{prefix} {message}")
        return

    print(f"{prefix} {message}", payload)


def _build_headers() -> dict[str, str]:
    try:
        return build_webmania_headers()
    except WebmaniaAuthError as exc:
        raise TaxClassServiceError(str(exc)) from exc


def _build_endpoint_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_ENDPOINT", ""))
    if custom_endpoint:
        endpoint = custom_endpoint.rstrip("/")
        return f"{endpoint}/"

    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/classe-imposto/"


def _extract_error_message(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()

    if isinstance(payload, dict):
        for key in ("error", "message", "msg", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        parts: list[str] = []
        for value in payload.values():
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
                continue
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        parts.append(item.strip())

        return "; ".join(parts)

    if isinstance(payload, list):
        parts: list[str] = []
        for item in payload:
            message = _extract_error_message(item)
            if message:
                parts.append(message)
        return "; ".join(parts)

    return ""


def _parse_json_response(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise TaxClassServiceError("Resposta inválida da API de classe de imposto.") from exc


def _request_exception_message(exc: requests.RequestException, *, default: str) -> str:
    if exc.response is None:
        return f"{default}: {exc}"

    payload: Any | None
    try:
        payload = exc.response.json()
    except ValueError:
        payload = exc.response.text

    extracted = _extract_error_message(payload)
    if extracted:
        return extracted

    if exc.response.text.strip():
        return f"{default}: {exc.response.text.strip()}"

    return f"{default}: {exc}"


def list_tax_classes() -> list[dict[str, Any]]:
    endpoint = _build_endpoint_url()
    _debug_print("GET endpoint", endpoint)

    try:
        response = requests.get(endpoint, headers=_build_headers(), timeout=30)
        _debug_print("GET status", response.status_code)
        _debug_print("GET body", response.text)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = _request_exception_message(exc, default="Falha ao listar classes de imposto")
        raise TaxClassServiceError(message) from exc

    payload = _parse_json_response(response)
    if not isinstance(payload, list):
        raise TaxClassServiceError("Resposta inválida da API ao listar classes de imposto.")

    return [item for item in payload if isinstance(item, dict)]


def save_tax_class(*, payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        raise TaxClassServiceError("Informe o payload da classe de imposto.")

    endpoint = _build_endpoint_url()

    try:
        response = requests.post(endpoint, json=payload, headers=_build_headers(), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = _request_exception_message(exc, default="Falha ao salvar classe de imposto")
        raise TaxClassServiceError(message) from exc

    data = _parse_json_response(response)
    if not isinstance(data, dict):
        raise TaxClassServiceError("Resposta inválida da API ao salvar classe de imposto.")

    error_message = _extract_error_message(data.get("error") or data.get("message") or data.get("msg"))
    if error_message:
        raise TaxClassServiceError(error_message)

    return data


def delete_tax_class(*, reference: str | list[str]) -> list[dict[str, Any]]:
    if isinstance(reference, str):
        normalized_reference = reference.strip()
        if not normalized_reference:
            raise TaxClassServiceError("Informe a referencia da classe de imposto para excluir.")
        payload_reference: str | list[str] = normalized_reference
    else:
        references = [item.strip() for item in reference if isinstance(item, str) and item.strip()]
        if not references:
            raise TaxClassServiceError("Informe ao menos uma referencia valida para excluir.")
        payload_reference = references

    endpoint = _build_endpoint_url()

    try:
        response = requests.delete(endpoint, json={"referencia": payload_reference}, headers=_build_headers(), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = _request_exception_message(exc, default="Falha ao excluir classe de imposto")
        raise TaxClassServiceError(message) from exc

    data = _parse_json_response(response)
    if not isinstance(data, list):
        if isinstance(data, dict):
            error_message = _extract_error_message(data.get("error") or data.get("message") or data.get("msg"))
            if error_message:
                raise TaxClassServiceError(error_message)
        raise TaxClassServiceError("Resposta invalida da API ao excluir classe de imposto.")

    for item in data:
        if not isinstance(item, dict):
            continue
        error_message = _extract_error_message(item.get("error") or item.get("message") or item.get("msg"))
        if error_message and "sucesso" not in error_message.lower():
            raise TaxClassServiceError(error_message)

    return [item for item in data if isinstance(item, dict)]
