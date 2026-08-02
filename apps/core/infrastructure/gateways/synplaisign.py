from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings

from apps.core.observability import observe_dependency_call


logger = logging.getLogger(__name__)


class SynplaiSignGatewayError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class SynplaiSignGatewayResult:
    envelope_id: str
    signing_token: str
    raw_response: dict[str, Any]


def _base_url() -> str:
    return str(getattr(settings, "SYNPLAISIGN_BASE_URL", "") or "").rstrip("/")


def _require_base_url() -> str:
    base_url = _base_url()
    if not base_url:
        raise SynplaiSignGatewayError("SYNPLAISIGN_BASE_URL nao configurado")
    return base_url


def _require_api_key(api_key: str) -> str:
    normalized = str(api_key or "").strip()
    if not normalized:
        raise SynplaiSignGatewayError("API key SynplaiSign ausente")
    return normalized


def _api_headers(*, api_key: str, content_type: str | None = "application/json") -> dict[str, str]:
    headers = {"x-api-key": _require_api_key(api_key)}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def create_api_key(*, master_key: str, name: str) -> dict[str, Any]:
    base_url = _require_base_url()
    payload = {"name": name}
    logger.info("synplaisign_api_key_create_start", extra={"name": name})

    try:
        with observe_dependency_call(
            logger=logger,
            dependency_type="http",
            dependency_name="synplaisign",
            operation="create_api_key",
            log_context={"name": name},
        ) as dependency_call:
            response = requests.post(
                f"{base_url}/api-keys",
                headers=_api_headers(api_key=master_key),
                json=payload,
                timeout=20,
            )
            dependency_call.set_http_status_code(response.status_code)
            response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        raise SynplaiSignGatewayError(f"Erro ao criar API key: {exc}. Resposta: {response_text}") from exc

    try:
        payload_data = response.json()
    except ValueError as exc:
        raise SynplaiSignGatewayError("Resposta invalida ao criar API key") from exc

    result = payload_data if isinstance(payload_data, dict) else {}
    logger.info("synplaisign_api_key_create_success", extra={"api_key_id": result.get("id"), "name": name})
    return result


def create_envelope(
    *,
    api_key: str,
    pdf_bytes: bytes,
    file_name: str,
    title: str,
    message: str,
    signatories: list[dict[str, Any]],
) -> SynplaiSignGatewayResult:
    base_url = _require_base_url()
    files = {"file": (file_name or "document.pdf", pdf_bytes, "application/pdf")}
    data = {
        "title": title,
        "message": message,
        "signatories": json.dumps(signatories, ensure_ascii=False),
    }

    logger.info(
        "synplaisign_envelope_create_start",
        extra={
            "file_name": file_name,
            "title": title,
            "signatories_count": len(signatories),
            "pdf_bytes_size": len(pdf_bytes),
        },
    )

    try:
        with observe_dependency_call(
            logger=logger,
            dependency_type="http",
            dependency_name="synplaisign",
            operation="create_envelope",
            log_context={"file_name": file_name, "title": title},
        ) as dependency_call:
            response = requests.post(
                f"{base_url}/envelopes",
                headers=_api_headers(api_key=api_key, content_type=None),
                data=data,
                files=files,
                timeout=30,
            )
            dependency_call.set_http_status_code(response.status_code)
            response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        logger.error(
            "synplaisign_envelope_create_failed",
            extra={
                "status_code": exc.response.status_code if getattr(exc, "response", None) is not None else None,
                "response_text": response_text[:1000] if response_text else "",
            },
        )
        raise SynplaiSignGatewayError(f"Erro ao criar envelope: {exc}. Resposta: {response_text}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise SynplaiSignGatewayError("Resposta invalida ao criar envelope") from exc

    if not isinstance(payload, dict):
        raise SynplaiSignGatewayError("Resposta invalida ao criar envelope")

    envelope_id = str(payload.get("id") or "").strip()
    if not envelope_id:
        raise SynplaiSignGatewayError("Resposta sem id do envelope")

    signing_token = ""
    signatories_payload = payload.get("signatories")
    if isinstance(signatories_payload, list):
        for item in signatories_payload:
            if not isinstance(item, dict):
                continue
            token = str(item.get("token") or "").strip()
            if token:
                signing_token = token
                break

    logger.info(
        "synplaisign_envelope_created",
        extra={"envelope_id": envelope_id, "has_signing_token": bool(signing_token)},
    )

    return SynplaiSignGatewayResult(
        envelope_id=envelope_id,
        signing_token=signing_token,
        raw_response=payload,
    )


def send_envelope(*, api_key: str, envelope_id: str) -> dict[str, Any]:
    base_url = _require_base_url()
    logger.info("synplaisign_envelope_send_start", extra={"envelope_id": envelope_id})

    try:
        with observe_dependency_call(
            logger=logger,
            dependency_type="http",
            dependency_name="synplaisign",
            operation="send_envelope",
            log_context={"envelope_id": envelope_id},
        ) as dependency_call:
            response = requests.post(
                f"{base_url}/envelopes/{envelope_id}/send",
                headers=_api_headers(api_key=api_key),
                timeout=20,
            )
            dependency_call.set_http_status_code(response.status_code)
            response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        logger.error(
            "synplaisign_envelope_send_failed",
            extra={
                "envelope_id": envelope_id,
                "status_code": exc.response.status_code if getattr(exc, "response", None) is not None else None,
                "response_text": response_text[:1000] if response_text else "",
            },
        )
        raise SynplaiSignGatewayError(f"Erro ao enviar envelope: {exc}. Resposta: {response_text}") from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    result = payload if isinstance(payload, dict) else {}
    logger.info("synplaisign_envelope_sent", extra={"envelope_id": envelope_id})
    return result


def get_signed_document_download_url(*, api_key: str, envelope_id: str) -> str:
    base_url = _require_base_url()
    logger.info("synplaisign_download_url_start", extra={"envelope_id": envelope_id})

    try:
        with observe_dependency_call(
            logger=logger,
            dependency_type="http",
            dependency_name="synplaisign",
            operation="get_signed_document_download_url",
            log_context={"envelope_id": envelope_id},
        ) as dependency_call:
            response = requests.get(
                f"{base_url}/envelopes/{envelope_id}/download",
                headers=_api_headers(api_key=api_key),
                timeout=20,
            )
            dependency_call.set_http_status_code(response.status_code)
            response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        logger.error(
            "synplaisign_download_url_failed",
            extra={
                "envelope_id": envelope_id,
                "status_code": exc.response.status_code if getattr(exc, "response", None) is not None else None,
            },
        )
        raise SynplaiSignGatewayError(f"Erro ao buscar URL do PDF assinado: {exc}. Resposta: {response_text}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise SynplaiSignGatewayError("Resposta invalida ao buscar URL do PDF assinado") from exc

    download_url = payload.get("url") if isinstance(payload, dict) else None
    if not isinstance(download_url, str) or not download_url.strip():
        raise SynplaiSignGatewayError("Resposta sem url para documento assinado")

    logger.info("synplaisign_download_url_success", extra={"envelope_id": envelope_id})
    return download_url.strip()


def download_signed_document(*, api_key: str, envelope_id: str) -> bytes:
    download_url = get_signed_document_download_url(api_key=api_key, envelope_id=envelope_id)
    logger.info("synplaisign_download_signed_start", extra={"envelope_id": envelope_id})

    try:
        with observe_dependency_call(
            logger=logger,
            dependency_type="http",
            dependency_name="synplaisign",
            operation="download_signed_document",
            log_context={"envelope_id": envelope_id},
        ) as dependency_call:
            response = requests.get(download_url, timeout=30)
            dependency_call.set_http_status_code(response.status_code)
            response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        raise SynplaiSignGatewayError(f"Erro ao baixar PDF assinado: {exc}. Resposta: {response_text}") from exc

    content_type = (response.headers.get("Content-Type") or "").lower()
    if "application/pdf" not in content_type and not response.content.startswith(b"%PDF"):
        raise SynplaiSignGatewayError("Arquivo retornado nao possui formato PDF")

    logger.info(
        "synplaisign_download_signed_success",
        extra={"envelope_id": envelope_id, "content_length": len(response.content)},
    )
    return bytes(response.content)


def list_webhooks(*, api_key: str) -> list[dict[str, Any]]:
    base_url = _require_base_url()
    logger.info("synplaisign_webhooks_list_start")

    try:
        with observe_dependency_call(
            logger=logger,
            dependency_type="http",
            dependency_name="synplaisign",
            operation="list_webhooks",
        ) as dependency_call:
            response = requests.get(
                f"{base_url}/webhooks",
                headers=_api_headers(api_key=api_key),
                timeout=20,
            )
            dependency_call.set_http_status_code(response.status_code)
            response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        raise SynplaiSignGatewayError(f"Erro ao listar webhooks: {exc}. Resposta: {response_text}") from exc

    payload = response.json()
    webhooks = payload if isinstance(payload, list) else []
    logger.info("synplaisign_webhooks_list_success", extra={"count": len(webhooks)})
    return [item for item in webhooks if isinstance(item, dict)]


def create_webhook(*, api_key: str, url: str, events: list[str] | None = None) -> dict[str, Any]:
    base_url = _require_base_url()
    expected_events = list(events or ["ENVELOPE_COMPLETED"])
    payload = {"url": url, "events": expected_events}

    logger.info("synplaisign_webhook_create_start", extra={"url": url, "events": expected_events})

    try:
        with observe_dependency_call(
            logger=logger,
            dependency_type="http",
            dependency_name="synplaisign",
            operation="create_webhook",
            log_context={"url": url},
        ) as dependency_call:
            response = requests.post(
                f"{base_url}/webhooks",
                headers=_api_headers(api_key=api_key),
                json=payload,
                timeout=20,
            )
            dependency_call.set_http_status_code(response.status_code)
            response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        raise SynplaiSignGatewayError(f"Erro ao criar webhook: {exc}. Resposta: {response_text}") from exc

    data = response.json()
    result = data if isinstance(data, dict) else {}
    logger.info("synplaisign_webhook_create_success", extra={"url": url, "webhook_id": result.get("id")})
    return result


def build_signing_url(*, token: str) -> str:
    base_url = _require_base_url()
    normalized_token = str(token or "").strip()
    if not normalized_token:
        raise SynplaiSignGatewayError("Token de assinatura ausente")
    return f"{base_url}/sign/{normalized_token}"
