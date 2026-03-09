from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import phonenumbers
from django.conf import settings
from django.core import signing
from django.http import HttpRequest
from django.urls import reverse
from phonenumbers import PhoneNumberFormat

from apps.core.documents.contract import SignatureRecipient


SIGNATURE_POSITION: dict[str, float] = {
    "x": 443.0,
    "y": 95.0,
    "width": 120.0,
    "height": 38.0,
}


class SignatureTokenError(Exception):
    pass


@dataclass(frozen=True)
class SignatureTokenPayload:
    document_id: int
    version: int


def normalize_signature_phone_number(raw_phone: object) -> str:
    if raw_phone is None:
        return ""

    e164_phone = getattr(raw_phone, "as_e164", "")
    if e164_phone:
        digits = re.sub(r"\D", "", str(e164_phone))
        return f"+{digits}" if digits else ""

    phone = str(raw_phone).strip()
    if not phone:
        return ""

    try:
        parsed_phone = phonenumbers.parse(
            phone,
            getattr(settings, "PHONENUMBER_DEFAULT_REGION", "BR"),
        )
    except phonenumbers.NumberParseException:
        parsed_phone = None

    if parsed_phone is not None and phonenumbers.is_valid_number(parsed_phone):
        return phonenumbers.format_number(parsed_phone, PhoneNumberFormat.E164)

    phone = re.sub(r"[^\d+]", "", phone)
    if not phone:
        return ""

    if phone.startswith("+"):
        return "+" + re.sub(r"\D", "", phone)

    digits = re.sub(r"\D", "", phone)
    if digits:
        if len(digits) in {10, 11}:
            return f"+55{digits}"
        return f"+{digits}"

    return ""


def build_absolute_app_url(*, path: str, request: HttpRequest | None = None) -> str:
    if request is not None:
        return request.build_absolute_uri(path)

    base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/")
    if not base_url:
        base_url = "http://localhost:8000"

    return f"{base_url}{path}"


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


def build_document_signature_url(*, route_name: str, token_salt: str, document_id_key: str, document_id: int, version: int, request: HttpRequest | None = None) -> str:
    token = build_document_signature_token(
        token_salt=token_salt,
        document_id_key=document_id_key,
        document_id=document_id,
        version=version,
    )
    path = reverse(route_name, args=[token])
    return build_absolute_app_url(path=path, request=request)


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
    signatory: dict[str, Any] = {
        "id": signatory_id,
        "name": recipient.name,
        "email": recipient.email,
        "qualification": qualification,
        "signingOrder": signing_order,
        "authMethod": "EMAIL",
    }

    normalized_phone = normalize_signature_phone_number(recipient.phone)
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
