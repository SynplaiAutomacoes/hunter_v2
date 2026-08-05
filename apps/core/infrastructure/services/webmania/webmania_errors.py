from __future__ import annotations

import re
from typing import Any

import requests


_ENDPOINT_SUFFIX_PATTERN = re.compile(r"\s*endpoint\s*:\s*.+$", flags=re.IGNORECASE)
_URL_PATTERN = re.compile(r"https?://[^\s]+", flags=re.IGNORECASE)
_ERROR_KEYS = ("error", "message", "msg", "detail", "erro", "mensagem")


def _omit_provider_name(message: str) -> str:
    cleaned = message
    for token in ("WEBMANIA", "Webmania", "webmania", "integração", "integraçao", "integracao"):
        cleaned = cleaned.replace(token, "")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.;:-")
    return cleaned


def sanitize_webmania_api_message(message: object, *, scope: str | None = None) -> str:
    normalized_message = str(message or "").strip()
    if not normalized_message:
        return ""

    normalized_message = _ENDPOINT_SUFFIX_PATTERN.sub("", normalized_message).strip()
    normalized_message = _URL_PATTERN.sub("", normalized_message).strip()
    normalized_message = re.sub(r"\s{2,}", " ", normalized_message).strip()

    if normalized_message.endswith(":"):
        normalized_message = normalized_message[:-1].strip()

    lowered_message = normalized_message.lower()
    if "configurar empresa" in lowered_message:
        if scope == "tax_class":
            return "Configure a empresa emissora antes de continuar com classes de imposto."
        if scope == "nfe":
            return "Configure a empresa emissora antes de emitir Nota Fiscal."
        if scope == "nfse":
            return "Configure a empresa emissora antes de emitir Nota Fiscal de Serviço."
        return "Configure a empresa emissora antes de prosseguir."

    return _omit_provider_name(normalized_message)


def extract_webmania_error_message(payload: Any, *, scope: str | None = None) -> str:
    if isinstance(payload, str):
        return sanitize_webmania_api_message(payload, scope=scope)

    if isinstance(payload, dict):
        for key in _ERROR_KEYS:
            value = payload.get(key)
            extracted = extract_webmania_error_message(value, scope=scope)
            if extracted:
                return extracted

        parts: list[str] = []
        for value in payload.values():
            if not isinstance(value, (dict, list)):
                continue

            extracted = extract_webmania_error_message(value, scope=scope)
            if extracted and extracted not in parts:
                parts.append(extracted)
        return "; ".join(parts)

    if isinstance(payload, list):
        list_parts: list[str] = []
        for item in payload:
            extracted = extract_webmania_error_message(item, scope=scope)
            if extracted and extracted not in list_parts:
                list_parts.append(extracted)
        return "; ".join(list_parts)

    return ""


def build_webmania_request_exception_message(
    exc: requests.RequestException,
    *,
    default: str,
    scope: str | None = None,
) -> str:
    if exc.response is not None:
        payload: Any | None
        try:
            payload = exc.response.json()
        except ValueError:
            payload = exc.response.text

        extracted = extract_webmania_error_message(payload, scope=scope)
        if extracted:
            return extracted

        response_text = sanitize_webmania_api_message(str(exc.response.text or ""), scope=scope)
        if response_text:
            return f"{default}: {response_text}"

    exc_message = sanitize_webmania_api_message(str(exc), scope=scope)
    if exc_message:
        return f"{default}: {exc_message}"

    return default
