from __future__ import annotations

from typing import Any

from apps.core.documents.contract import SignatureDeliveryResult
from apps.core.documents.gateways.supersign import (
    SuperSignGatewayError,
    download_signed_document,
    get_signed_document_download_url,
    send_pdf_for_signature,
)


class SignatureDeliveryServiceError(Exception):
    pass


def send_document_for_signature(
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
) -> SignatureDeliveryResult:
    try:
        result = send_pdf_for_signature(
            pdf_bytes=pdf_bytes,
            file_name=file_name,
            document_ref_id=document_ref_id,
            title=title,
            message=message,
            signatory=signatory,
            observers=observers,
            fields=fields,
            folder_id=folder_id,
        )
    except SuperSignGatewayError as exc:
        raise SignatureDeliveryServiceError(str(exc)) from exc

    return SignatureDeliveryResult(
        envelope_id=result.envelope_id,
        document_id=result.document_id,
        provider="supersign",
        raw_response=result.raw_response,
    )


def get_signed_document_url(*, document_id: str) -> str:
    try:
        return get_signed_document_download_url(document_id=document_id)
    except SuperSignGatewayError as exc:
        raise SignatureDeliveryServiceError(str(exc)) from exc


def download_signed_document_content(*, document_id: str) -> bytes:
    try:
        return download_signed_document(document_id=document_id)
    except SuperSignGatewayError as exc:
        raise SignatureDeliveryServiceError(str(exc)) from exc
