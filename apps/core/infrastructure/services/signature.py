from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core import signing
from django.http import HttpRequest
from django.urls import reverse

from apps.core.domain.contracts.documents import (
    SIGNATURE_POSITION,
    SignatureRecipient,
    SignatureTokenError,
    SignatureTokenPayload,
    normalize_signature_phone_number,
)


class SignatureDeliveryServiceError(Exception):
    pass


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
    """Build provider-neutral signatory payload used by adapters.

    Phone is forwarded to SynplaiSign as digits + deliveryChannel (EMAIL/WHATSAPP/BOTH).
    """
    region = getattr(settings, "PHONENUMBER_DEFAULT_REGION", "BR")
    signatory: dict[str, Any] = {
        "id": signatory_id,
        "name": recipient.name,
        "email": recipient.email,
        "qualification": qualification,
        "signingOrder": signing_order,
    }

    normalized_phone = normalize_signature_phone_number(recipient.phone, default_region=region)
    if normalized_phone:
        signatory["phoneNumber"] = normalized_phone

    return signatory, []


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
