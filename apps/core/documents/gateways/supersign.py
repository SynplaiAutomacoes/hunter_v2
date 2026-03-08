from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings


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


def get_signed_document_download_url(*, document_id: str) -> str:
    base_url = settings.SUPERSIGN_BASE_URL.rstrip("/")
    try:
        response = requests.get(
            f"{base_url}/v2/documents/{document_id}/download",
            headers=_supersign_headers(),
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        raise SuperSignGatewayError(f"Erro ao buscar downloadUrl do documento assinado: {exc}. Resposta: {response_text}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise SuperSignGatewayError("Resposta invalida ao buscar downloadUrl do documento assinado") from exc

    download_url = data.get("downloadUrl") if isinstance(data, dict) else None
    if not isinstance(download_url, str) or not download_url.strip():
        raise SuperSignGatewayError("Resposta sem downloadUrl para documento assinado")

    return download_url.strip()


def download_signed_document(*, document_id: str) -> bytes:
    download_url = get_signed_document_download_url(document_id=document_id)

    try:
        response = requests.get(download_url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        raise SuperSignGatewayError(f"Erro ao baixar PDF assinado: {exc}. Resposta: {response_text}") from exc

    content_type = (response.headers.get("Content-Type") or "").lower()
    pdf_signature = b"%PDF"
    if "application/pdf" not in content_type and not response.content.startswith(pdf_signature):
        raise SuperSignGatewayError("Arquivo retornado nao possui formato PDF")

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
        raise SuperSignGatewayError(f"Erro ao criar envelope: {exc}. Resposta: {response_text}") from exc

    create_data = create_resp.json()
    envelope_id = create_data.get("envelopeId")
    upload_details = create_data.get("uploadDetails") or []
    if not envelope_id or not upload_details:
        raise SuperSignGatewayError("Resposta sem envelopeId/uploadDetails")

    first_upload = upload_details[0]
    document_id = first_upload.get("documentId")
    upload_url = first_upload.get("uploadUrl")
    if not document_id or not upload_url:
        raise SuperSignGatewayError("uploadDetails incompleto")

    upload_headers = {"Content-Type": "application/pdf", "x-goog-meta-documentid": str(document_id)}
    try:
        upload_resp = requests.put(
            upload_url,
            data=pdf_bytes,
            headers=upload_headers,
            timeout=30,
        )
        upload_resp.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        raise SuperSignGatewayError(f"Erro ao enviar arquivo para uploadUrl: {exc}. Resposta: {response_text}") from exc

    return SuperSignGatewayResult(
        envelope_id=str(envelope_id),
        document_id=str(document_id),
        raw_response=create_data,
    )
