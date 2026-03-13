from __future__ import annotations

from typing import Any

from apps.core.documents.contract import SignatureDeliveryResult
from apps.core.documents.gateways.supersign import (
    SuperSignGatewayError,
    create_supersign_webhook as create_supersign_webhook_request,
    download_signed_document,
    get_supersign_envelope_signed_document_id,
    get_signed_document_download_url,
    list_supersign_webhooks as list_supersign_webhooks_request,
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


def resolve_signed_document_id(*, document_id: str | None = None, envelope_id: str | None = None) -> str:
    if document_id:
        return document_id

    if not envelope_id:
        raise SignatureDeliveryServiceError("Nenhum identificador do documento assinado foi informado")

    try:
        return get_supersign_envelope_signed_document_id(envelope_id=envelope_id)
    except SuperSignGatewayError as exc:
        raise SignatureDeliveryServiceError(str(exc)) from exc


def list_signature_webhooks() -> list[dict[str, Any]]:
    try:
        return list_supersign_webhooks_request()
    except SuperSignGatewayError as exc:
        raise SignatureDeliveryServiceError(str(exc)) from exc


def create_signature_webhook(*, url: str, events: list[str] | None = None, is_active: bool = True) -> dict[str, Any]:
    try:
        return create_supersign_webhook_request(url=url, events=events, is_active=is_active)
    except SuperSignGatewayError as exc:
        raise SignatureDeliveryServiceError(str(exc)) from exc


def ensure_signature_webhook(*, webhook_url: str, events: list[str] | None = None) -> dict[str, Any]:
    expected_events = list(events or ["ENVELOPE_COMPLETED"])
    existing = list_signature_webhooks()

    for webhook in existing:
        webhook_events = webhook.get("events")
        if webhook.get("url") == webhook_url and isinstance(webhook_events, list) and all(event in webhook_events for event in expected_events):
            return webhook

    return create_signature_webhook(url=webhook_url, events=expected_events, is_active=True)


def download_signed_document_content(*, document_id: str | None = None, envelope_id: str | None = None) -> bytes:
    resolved_document_id = resolve_signed_document_id(document_id=document_id, envelope_id=envelope_id)

    try:
        return download_signed_document(document_id=resolved_document_id)
    except SuperSignGatewayError as exc:
        raise SignatureDeliveryServiceError(str(exc)) from exc
