from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import phonenumbers
from phonenumbers import PhoneNumberFormat


SIGNATURE_POSITION: dict[str, float] = {
    "x": 443.0,
    "y": 180.0,
    "width": 120.0,
    "height": 38.0,
}


@dataclass(frozen=True)
class DocumentRenderRequest:
    template_name: str
    context: dict[str, Any]
    filename: str
    content_type: str = "application/pdf"


@dataclass(frozen=True)
class DocumentPayload:
    content: bytes
    filename: str
    content_type: str = "application/pdf"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SignatureRecipient:
    name: str
    email: str
    phone: object = ""


@dataclass(frozen=True)
class SignatureDeliveryResult:
    envelope_id: str
    document_id: str
    provider: str
    raw_response: dict[str, Any]


class SignatureTokenError(Exception):
    pass


@dataclass(frozen=True)
class SignatureTokenPayload:
    document_id: int
    version: int


def normalize_signature_phone_number(raw_phone: object, default_region: str = "BR") -> str:
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
        parsed_phone = phonenumbers.parse(phone, default_region)
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
