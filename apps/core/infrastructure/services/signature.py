from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core import signing
from django.http import HttpRequest
from django.urls import reverse

from apps.core.domain.contracts.documents import (
    SIGNATURE_POSITION,
    SignatureDeliveryResult,
    SignatureRecipient,
    SignatureTokenError,
    SignatureTokenPayload,
    normalize_signature_phone_number,
)
from apps.core.infrastructure.gateways.supersign import (
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


def build_document_signature_payload(*, document_id_key: str, document_id: int, version: int) -> dict[str, int]:
    return {
        document_id_key: document_id,
        "version": version,
    }


def build_document_signature_token(*, token_salt: str, document_id_key: str, document_id: int, version: int) -> str:
    payload = build_document_signature_payload(
        document_id_key=document_id_key,
        document_id=document_id,
        version=version,
    )
    return signing.dumps(payload, salt=token_salt)


def parse_document_signature_token(*, token: str, token_salt: str, document_id_key: str) -> SignatureTokenPayload:
    try:
        payload = signing.loads(token, salt=token_salt)
        document_id = int(payload[document_id_key])
        version = int(payload["version"])
    except (signing.BadSignature, KeyError, TypeError, ValueError) as exc:
        raise SignatureTokenError("Invalid signature token") from exc

    return SignatureTokenPayload(
        document_id=document_id,
        version=version,
    )


def build_signature_signatory_and_observers(
    *,
    signatory_id: str,
    recipient: SignatureRecipient,
    qualification: str = "Cliente",
    signing_order: int = 0,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    region = getattr(settings, "PHONENUMBER_DEFAULT_REGION", "BR")
    signatory: dict[str, Any] = {
        "id": signatory_id,
        "name": recipient.name,
        "email": recipient.email,
        "qualification": qualification,
        "signingOrder": signing_order,
        "authMethod": "EMAIL",
    }

    normalized_phone = normalize_signature_phone_number(recipient.phone, default_region=region)
    observers: list[dict[str, Any]] = []

    if normalized_phone:
        signatory["authMethod"] = "WHATSAPP"
        signatory["phoneNumber"] = normalized_phone
        observers.append(
            {
                "email": recipient.email,
                "notifyOnSent": True,
                "notifyOnCompletion": True,
            }
        )

    return signatory, observers


def build_signature_fields(*, document_ref_id: str, signatory_ref_id: str, page_number: int, position: dict[str, float] | None = None) -> list[dict[str, Any]]:
    return [
        {
            "type": "SIGNATURE",
            "documentId": document_ref_id,
            "signatoryId": signatory_ref_id,
            "pageNumber": page_number,
            "position": position or SIGNATURE_POSITION,
            "properties": {},
        }
    ]


def build_absolute_app_url(*, path: str, request: HttpRequest | None = None) -> str:
    if request is not None:
        return request.build_absolute_uri(path)

    base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/")
    if not base_url:
        base_url = "http://localhost:8000"

    return f"{base_url}{path}"


def build_document_signature_url(*, route_name: str, token_salt: str, document_id_key: str, document_id: int, version: int, request: HttpRequest | None = None) -> str:
    token = build_document_signature_token(
        token_salt=token_salt,
        document_id_key=document_id_key,
        document_id=document_id,
        version=version,
    )
    path = reverse(route_name, args=[token])
    return build_absolute_app_url(path=path, request=request)
