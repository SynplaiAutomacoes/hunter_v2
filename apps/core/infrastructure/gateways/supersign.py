from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings


logger = logging.getLogger(__name__)


class SuperSignGatewayError(Exception):
    pass


@dataclass
class SuperSignGatewayResult:
    envelope_id: str
    document_id: str
    raw_response: dict[str, Any]


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
            response = requests.get(
                f"{base_url}/v2/documents/{document_id}/download",
                headers=_supersign_download_headers(include_authorization=include_authorization),
                params={"type": "signed"},
                timeout=20,
            )
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
        logger.error("supersign_download_url_missing", extra={"document_id": document_id, "response_keys": list(data.keys()) if isinstance(data, dict) else None})
        raise SuperSignGatewayError("Resposta sem downloadUrl para documento assinado")

    logger.info("supersign_download_url_success", extra={"document_id": document_id, "download_url_length": len(download_url.strip())})
    return download_url.strip()


def get_supersign_envelope_signed_document_id(*, envelope_id: str) -> str:
    base_url = settings.SUPERSIGN_BASE_URL.rstrip("/")

    logger.info("supersign_envelope_details_start", extra={"envelope_id": envelope_id})

    try:
        response = requests.get(
            f"{base_url}/v2/envelopes/{envelope_id}",
            headers=_supersign_headers(),
            timeout=20,
        )
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
        logger.error("supersign_envelope_details_no_documents", extra={"envelope_id": envelope_id, "envelope_status": envelope_status, "response_keys": list(data.keys()) if isinstance(data, dict) else None})
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


def list_supersign_webhooks() -> list[dict[str, Any]]:
    base_url = settings.SUPERSIGN_BASE_URL.rstrip("/")
    logger.info("supersign_webhooks_list_start")
    try:
        response = requests.get(
            f"{base_url}/v2/webhooks/",
            headers=_supersign_headers(),
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        logger.error("supersign_webhooks_list_failed", extra={"status_code": exc.response.status_code if exc.response is not None else None})
        raise SuperSignGatewayError(f"Erro ao listar webhooks: {exc}. Resposta: {response_text}") from exc

    data = response.json()
    webhooks = data if isinstance(data, list) else []
    logger.info("supersign_webhooks_list_success", extra={"count": len(webhooks)})
    return webhooks


def create_supersign_webhook(*, url: str, events: list[str] | None = None, is_active: bool = True) -> dict[str, Any]:
    base_url = settings.SUPERSIGN_BASE_URL.rstrip("/")
    payload = {
        "url": url,
        "events": events or ["ENVELOPE_COMPLETED"],
        "isActive": is_active,
    }

    logger.info("supersign_webhook_create_start", extra={"url": url, "events": events or ["ENVELOPE_COMPLETED"]})

    try:
        response = requests.post(
            f"{base_url}/v2/webhooks/",
            json=payload,
            headers=_supersign_headers(),
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        logger.error(
            "supersign_webhook_create_failed",
            extra={
                "url": url,
                "status_code": exc.response.status_code if exc.response is not None else None,
            },
        )
        raise SuperSignGatewayError(f"Erro ao criar webhook: {exc}. Resposta: {response_text}") from exc

    data = response.json()
    result = data if isinstance(data, dict) else {}
    logger.info("supersign_webhook_create_success", extra={"url": url, "webhook_id": result.get("id")})
    return result


def download_signed_document(*, document_id: str) -> bytes:
    download_url = get_signed_document_download_url(document_id=document_id)

    logger.info("supersign_download_signed_start", extra={"document_id": document_id})

    try:
        response = requests.get(download_url, timeout=30)
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
    pdf_signature = b"%PDF"
    if "application/pdf" not in content_type and not response.content.startswith(pdf_signature):
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

    return response.content


def send_pdf_for_signature(
    *,
    pdf_bytes: bytes,
    file_name: str,
    document_ref_id: str,
    title: str,
    message: str,
    signatory: dict[str, Any],
    observers: list[dict[str, Any]],
    fields: list[dict[str, Any]],
    folder_id: str,
) -> SuperSignGatewayResult:
    create_payload = {
        "folderId": folder_id,
        "title": title,
        "message": message,
        "documents": [
            {
                "id": document_ref_id,
                "fileName": file_name,
                "contentType": "application/pdf",
            }
        ],
        "signatories": [signatory],
        "observers": observers,
        "fields": fields,
    }

    base_url = settings.SUPERSIGN_BASE_URL.rstrip("/")

    logger.info(
        "supersign_envelope_create_start",
        extra={
            "document_ref_id": document_ref_id,
            "file_name": file_name,
            "title": title,
            "signatory_email": signatory.get("email", ""),
            "pdf_bytes_size": len(pdf_bytes),
            "folder_id": folder_id,
        },
    )

    try:
        create_resp = requests.post(
            f"{base_url}/v2/envelopes/",
            json=create_payload,
            headers=_supersign_headers(),
            timeout=20,
        )
        create_resp.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        logger.error(
            "supersign_envelope_create_failed",
            extra={
                "document_ref_id": document_ref_id,
                "status_code": exc.response.status_code if exc.response is not None else None,
                "response_text": response_text[:1000] if response_text else "",
            },
        )
        raise SuperSignGatewayError(f"Erro ao criar envelope: {exc}. Resposta: {response_text}") from exc

    create_data = create_resp.json()
    envelope_id = create_data.get("envelopeId")
    upload_details = create_data.get("uploadDetails") or []
    if not envelope_id or not upload_details:
        logger.error(
            "supersign_envelope_create_missing_fields",
            extra={
                "document_ref_id": document_ref_id,
                "has_envelope_id": bool(envelope_id),
                "upload_details_count": len(upload_details),
                "response_keys": list(create_data.keys()),
            },
        )
        raise SuperSignGatewayError("Resposta sem envelopeId/uploadDetails")

    first_upload = upload_details[0]
    document_id = first_upload.get("documentId")
    upload_url = first_upload.get("uploadUrl")
    if not document_id or not upload_url:
        logger.error(
            "supersign_envelope_create_incomplete_upload_details",
            extra={
                "document_ref_id": document_ref_id,
                "envelope_id": envelope_id,
                "has_document_id": bool(document_id),
                "has_upload_url": bool(upload_url),
                "upload_details_keys": list(first_upload.keys()),
            },
        )
        raise SuperSignGatewayError("uploadDetails incompleto")

    logger.info(
        "supersign_envelope_created",
        extra={
            "document_ref_id": document_ref_id,
            "envelope_id": envelope_id,
            "document_id": document_id,
        },
    )

    upload_headers = {"Content-Type": "application/pdf", "x-goog-meta-documentid": str(document_id)}
    try:
        logger.info(
            "supersign_pdf_upload_start",
            extra={
                "document_ref_id": document_ref_id,
                "envelope_id": envelope_id,
                "document_id": document_id,
                "pdf_bytes_size": len(pdf_bytes),
            },
        )
        upload_resp = requests.put(
            upload_url,
            data=pdf_bytes,
            headers=upload_headers,
            timeout=30,
        )
        upload_resp.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        logger.error(
            "supersign_pdf_upload_failed",
            extra={
                "document_ref_id": document_ref_id,
                "envelope_id": envelope_id,
                "document_id": document_id,
                "status_code": exc.response.status_code if exc.response is not None else None,
                "response_text": response_text[:1000] if response_text else "",
            },
        )
        raise SuperSignGatewayError(f"Erro ao enviar arquivo para uploadUrl: {exc}. Resposta: {response_text}") from exc

    logger.info(
        "supersign_pdf_uploaded",
        extra={
            "document_ref_id": document_ref_id,
            "envelope_id": envelope_id,
            "document_id": document_id,
        },
    )

    return SuperSignGatewayResult(
        envelope_id=str(envelope_id),
        document_id=str(document_id),
        raw_response=create_data,
    )
