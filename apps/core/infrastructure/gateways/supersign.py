"""SuperSign gateway — download-only helpers for legacy signed PDFs."""

from __future__ import annotations

import logging

import requests
from django.conf import settings

from apps.core.observability import observe_dependency_call


logger = logging.getLogger(__name__)


class SuperSignGatewayError(Exception):
    pass


def _supersign_headers() -> dict[str, str]:
    return {
        "x-account-id": settings.SUPERSIGN_ACCOUNT_ID,
        "Authorization": f"Bearer {settings.SUPERSIGN_API_KEY}",
        "Content-Type": "application/json",
    }


def _supersign_download_headers(*, include_authorization: bool) -> dict[str, str]:
    headers = {"x-account-id": settings.SUPERSIGN_ACCOUNT_ID}
    if include_authorization:
        headers["Authorization"] = f"Bearer {settings.SUPERSIGN_API_KEY}"
    return headers


def get_signed_document_download_url(*, document_id: str) -> str:
    base_url = settings.SUPERSIGN_BASE_URL.rstrip("/")
    last_exception: requests.RequestException | None = None

    logger.info("supersign_download_url_start", extra={"document_id": document_id})

    for include_authorization in (False, True):
        try:
            with observe_dependency_call(
                logger=logger,
                dependency_type="http",
                dependency_name="supersign",
                operation="get_signed_document_download_url",
                log_context={"document_id": document_id, "include_authorization": include_authorization},
            ) as dependency_call:
                response = requests.get(
                    f"{base_url}/v2/documents/{document_id}/download",
                    headers=_supersign_download_headers(include_authorization=include_authorization),
                    params={"type": "signed"},
                    timeout=20,
                )
                dependency_call.set_http_status_code(response.status_code)
                response.raise_for_status()
            break
        except requests.RequestException as exc:
            last_exception = exc
            status_code = exc.response.status_code if exc.response is not None else None
            logger.warning(
                "supersign_download_url_retry",
                extra={
                    "document_id": document_id,
                    "status_code": status_code,
                    "include_authorization": include_authorization,
                },
            )
            if status_code not in {401, 403} or include_authorization:
                response_text = exc.response.text if exc.response is not None else ""
                raise SuperSignGatewayError(f"Erro ao buscar downloadUrl do documento assinado: {exc}. Resposta: {response_text}") from exc
    else:
        response_text = last_exception.response.text if last_exception is not None and last_exception.response is not None else ""
        raise SuperSignGatewayError(f"Erro ao buscar downloadUrl do documento assinado: {last_exception}. Resposta: {response_text}") from last_exception

    try:
        data = response.json()
    except ValueError as exc:
        logger.error("supersign_download_url_invalid_json", extra={"document_id": document_id})
        raise SuperSignGatewayError("Resposta invalida ao buscar downloadUrl do documento assinado") from exc

    download_url = data.get("downloadUrl") or data.get("url") if isinstance(data, dict) else None
    if not isinstance(download_url, str) or not download_url.strip():
        logger.error(
            "supersign_download_url_missing",
            extra={"document_id": document_id, "response_keys": list(data.keys()) if isinstance(data, dict) else None},
        )
        raise SuperSignGatewayError("Resposta sem downloadUrl para documento assinado")

    logger.info("supersign_download_url_success", extra={"document_id": document_id, "download_url_length": len(download_url.strip())})
    return download_url.strip()


def get_supersign_envelope_signed_document_id(*, envelope_id: str) -> str:
    base_url = settings.SUPERSIGN_BASE_URL.rstrip("/")

    logger.info("supersign_envelope_details_start", extra={"envelope_id": envelope_id})

    try:
        with observe_dependency_call(
            logger=logger,
            dependency_type="http",
            dependency_name="supersign",
            operation="get_envelope_details",
            log_context={"envelope_id": envelope_id},
        ) as dependency_call:
            response = requests.get(
                f"{base_url}/v2/envelopes/{envelope_id}",
                headers=_supersign_headers(),
                timeout=20,
            )
            dependency_call.set_http_status_code(response.status_code)
            response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        logger.error(
            "supersign_envelope_details_failed",
            extra={
                "envelope_id": envelope_id,
                "status_code": exc.response.status_code if exc.response is not None else None,
                "response_text": response_text[:500] if response_text else "",
            },
        )
        raise SuperSignGatewayError(f"Erro ao buscar detalhes do envelope: {exc}. Resposta: {response_text}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        logger.error("supersign_envelope_details_invalid_json", extra={"envelope_id": envelope_id})
        raise SuperSignGatewayError("Resposta invalida ao buscar detalhes do envelope") from exc

    envelope_status = data.get("status") if isinstance(data, dict) else None
    documents = data.get("documents") if isinstance(data, dict) else None
    if not isinstance(documents, list):
        logger.error(
            "supersign_envelope_details_no_documents",
            extra={
                "envelope_id": envelope_id,
                "envelope_status": envelope_status,
                "response_keys": list(data.keys()) if isinstance(data, dict) else None,
            },
        )
        raise SuperSignGatewayError("Resposta sem documentos do envelope")

    first_document_id = ""
    for document in documents:
        if not isinstance(document, dict):
            continue

        document_id = document.get("id")
        signed_file_key = document.get("signedFileKey")
        if not first_document_id and isinstance(document_id, str) and document_id.strip():
            first_document_id = document_id.strip()
        if isinstance(document_id, str) and document_id.strip() and isinstance(signed_file_key, str) and signed_file_key.strip():
            logger.info(
                "supersign_envelope_details_signed_doc_found",
                extra={
                    "envelope_id": envelope_id,
                    "document_id": document_id.strip(),
                    "envelope_status": envelope_status,
                },
            )
            return document_id.strip()

    if envelope_status == "COMPLETED" and first_document_id:
        logger.info(
            "supersign_envelope_details_signed_doc_fallback",
            extra={
                "envelope_id": envelope_id,
                "document_id": first_document_id,
                "envelope_status": envelope_status,
            },
        )
        return first_document_id

    logger.warning(
        "supersign_envelope_details_no_signed_doc",
        extra={
            "envelope_id": envelope_id,
            "envelope_status": envelope_status,
            "documents_count": len(documents),
            "first_document_id": first_document_id,
        },
    )
    raise SuperSignGatewayError("Envelope ainda nao possui documento assinado disponivel")


def download_signed_document(*, document_id: str) -> bytes:
    download_url = get_signed_document_download_url(document_id=document_id)

    logger.info("supersign_download_signed_start", extra={"document_id": document_id})

    try:
        with observe_dependency_call(
            logger=logger,
            dependency_type="http",
            dependency_name="supersign",
            operation="download_signed_document",
            log_context={"document_id": document_id},
        ) as dependency_call:
            response = requests.get(download_url, timeout=30)
            dependency_call.set_http_status_code(response.status_code)
            response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        logger.error(
            "supersign_download_signed_failed",
            extra={
                "document_id": document_id,
                "status_code": exc.response.status_code if exc.response is not None else None,
                "response_text": response_text[:500] if response_text else "",
            },
        )
        raise SuperSignGatewayError(f"Erro ao baixar PDF assinado: {exc}. Resposta: {response_text}") from exc

    content_type = (response.headers.get("Content-Type") or "").lower()
    if "application/pdf" not in content_type and not response.content.startswith(b"%PDF"):
        logger.error(
            "supersign_download_signed_not_pdf",
            extra={
                "document_id": document_id,
                "content_type": content_type,
                "content_length": len(response.content),
            },
        )
        raise SuperSignGatewayError("Arquivo retornado nao possui formato PDF")

    logger.info(
        "supersign_download_signed_success",
        extra={
            "document_id": document_id,
            "content_type": content_type,
            "content_length": len(response.content),
        },
    )

    return bytes(response.content)
