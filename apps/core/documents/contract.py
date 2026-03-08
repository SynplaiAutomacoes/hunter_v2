from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    phone: str = ""


@dataclass(frozen=True)
class SignatureDeliveryResult:
    envelope_id: str
    document_id: str
    provider: str
    raw_response: dict[str, Any]
