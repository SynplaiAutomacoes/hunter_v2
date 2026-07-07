from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from apps.core.domain.contracts.signature import (
    ISignatureService,
    SignatureSendRequest,
    SignatureSendResult,
    SignatureServiceError,
)
from apps.core.infrastructure.gateways.supersign import (
    SuperSignGatewayError,
    create_supersign_webhook,
    list_supersign_webhooks,
    send_pdf_for_signature,
)
from apps.core.infrastructure.services.signature import (
    SignatureDeliveryServiceError,
    build_document_signature_payload,
    build_document_signature_token,
    build_document_signature_url,
    build_signature_fields,
    build_signature_signatory_and_observers,
    download_signed_document_content,
    ensure_signature_webhook,
    get_signed_document_url,
    parse_document_signature_token,
)


class SuperSignSignatureService(ISignatureService):
    def send_document(self, request: SignatureSendRequest) -> SignatureSendResult:
        try:
            result = send_pdf_for_signature(
                pdf_bytes=request.pdf_bytes,
                file_name=request.file_name,
                document_ref_id=request.document_ref_id,
                title=request.title,
                message=request.message,
                signatory=request.signatory,
                observers=request.observers,
                fields=request.fields,
                folder_id=request.folder_id,
            )
        except SuperSignGatewayError as exc:
            raise SignatureServiceError(str(exc)) from exc

        return SignatureSendResult(
            envelope_id=result.envelope_id,
            document_id=result.document_id,
            provider="supersign",
            raw_response=result.raw_response,
        )

    def get_signed_document_url(self, *, document_id: str) -> str:
        try:
            return get_signed_document_url(document_id=document_id)
        except SignatureServiceError:
            raise

    def download_signed_document(self, *, document_id: str | None = None, envelope_id: str | None = None) -> bytes:
        try:
            return download_signed_document_content(document_id=document_id, envelope_id=envelope_id)
        except SignatureDeliveryServiceError as exc:
            raise SignatureServiceError(str(exc)) from exc
        except SignatureServiceError:
            raise

    def list_webhooks(self) -> list[dict[str, Any]]:
        from apps.core.infrastructure.gateways.supersign import SuperSignGatewayError

        try:
            return list_supersign_webhooks()
        except SuperSignGatewayError as exc:
            raise SignatureServiceError(str(exc)) from exc

    def create_webhook(self, *, url: str, events: list[str] | None = None, is_active: bool = True) -> dict[str, Any]:
        from apps.core.infrastructure.gateways.supersign import SuperSignGatewayError

        try:
            return create_supersign_webhook(url=url, events=events, is_active=is_active)
        except SuperSignGatewayError as exc:
            raise SignatureServiceError(str(exc)) from exc

    def ensure_webhook(self, *, webhook_url: str, events: list[str] | None = None) -> dict[str, Any]:
        try:
            return ensure_signature_webhook(webhook_url=webhook_url, events=events)
        except SignatureServiceError:
            raise

    def build_signature_payload(self, *, document_id_key: str, document_id: int, version: int) -> dict[str, int]:
        return build_document_signature_payload(
            document_id_key=document_id_key,
            document_id=document_id,
            version=version,
        )

    def build_signature_token(self, *, token_salt: str, document_id_key: str, document_id: int, version: int) -> str:
        return build_document_signature_token(
            token_salt=token_salt,
            document_id_key=document_id_key,
            document_id=document_id,
            version=version,
        )

    def parse_signature_token(self, *, token: str, token_salt: str, document_id_key: str) -> dict[str, Any]:
        from apps.core.domain.contracts.documents import SignatureTokenPayload

        result: SignatureTokenPayload = parse_document_signature_token(
            token=token,
            token_salt=token_salt,
            document_id_key=document_id_key,
        )
        return {"document_id": result.document_id, "version": result.version}

    def build_signatory_and_observers(
        self,
        *,
        signatory_id: str,
        recipient: Any,
        qualification: str = "Cliente",
        signing_order: int = 0,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        return build_signature_signatory_and_observers(
            signatory_id=signatory_id,
            recipient=recipient,
            qualification=qualification,
            signing_order=signing_order,
        )

    def build_signature_fields(
        self,
        *,
        document_ref_id: str,
        signatory_ref_id: str,
        page_number: int,
        position: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        return build_signature_fields(
            document_ref_id=document_ref_id,
            signatory_ref_id=signatory_ref_id,
            page_number=page_number,
            position=position,
        )

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
        return build_document_signature_url(
            route_name=route_name,
            token_salt=token_salt,
            document_id_key=document_id_key,
            document_id=document_id,
            version=version,
            request=request,
        )
