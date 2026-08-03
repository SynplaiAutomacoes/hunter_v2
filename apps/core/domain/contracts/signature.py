from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from django.http import HttpRequest


class SignatureServiceError(Exception):
    pass


@dataclass(frozen=True)
class SignatureSendRequest:
    document_bytes: bytes
    file_name: str
    document_ref_id: str
    title: str
    message: str
    signatory: dict[str, Any]
    observers: list[dict[str, Any]]
    fields: list[dict[str, Any]]
    folder_id: str = ""
    api_key: str = ""
    whatsapp_instance: str = ""
    content_type: str = "application/pdf"

    @property
    def pdf_bytes(self) -> bytes:
        """Deprecated alias for document_bytes."""
        return self.document_bytes


@dataclass(frozen=True)
class SignatureSendResult:
    envelope_id: str
    document_id: str
    provider: str
    raw_response: dict[str, Any]
    signing_url: str = ""


class ISignatureService(ABC):
    @abstractmethod
    def send_document(self, request: SignatureSendRequest) -> SignatureSendResult:
        ...

    @abstractmethod
    def get_signed_document_url(self, *, document_id: str, api_key: str = "") -> str:
        ...

    @abstractmethod
    def download_signed_document(self, *, document_id: str | None = None, envelope_id: str | None = None, api_key: str = "") -> bytes:
        ...

    @abstractmethod
    def list_webhooks(self, *, api_key: str = "") -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def create_webhook(self, *, url: str, events: list[str] | None = None, is_active: bool = True, api_key: str = "") -> dict[str, Any]:
        ...

    @abstractmethod
    def ensure_webhook(self, *, webhook_url: str, events: list[str] | None = None, api_key: str = "") -> dict[str, Any]:
        ...

    @abstractmethod
    def build_signature_payload(self, *, document_id_key: str, document_id: int, version: int) -> dict[str, int]:
        ...

    @abstractmethod
    def build_signature_token(self, *, token_salt: str, document_id_key: str, document_id: int, version: int) -> str:
        ...

    @abstractmethod
    def parse_signature_token(self, *, token: str, token_salt: str, document_id_key: str) -> dict[str, Any]:
        ...

    @abstractmethod
    def build_signatory_and_observers(
        self,
        *,
        signatory_id: str,
        recipient: Any,
        qualification: str = "Cliente",
        signing_order: int = 0,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        ...

    @abstractmethod
    def build_signature_fields(
        self,
        *,
        document_ref_id: str,
        signatory_ref_id: str,
        page_number: int,
        position: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def build_signature_url(
        self,
        *,
        route_name: str,
        token_salt: str,
        document_id_key: str,
        document_id: int,
        version: int,
        request: HttpRequest | None = None,
    ) -> str:
        ...
