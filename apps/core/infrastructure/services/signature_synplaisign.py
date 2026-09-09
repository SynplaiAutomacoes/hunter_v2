from __future__ import annotations

import logging
import re
from typing import Any, Literal

from django.http import HttpRequest

from apps.core.domain.contracts.documents import SIGNATURE_POSITION
from apps.core.domain.contracts.signature import (
    ISignatureService,
    SignatureSendRequest,
    SignatureSendResult,
    SignatureServiceError,
)
from apps.core.infrastructure.gateways import synplaisign as gateway
from apps.core.infrastructure.services.signature import (
    build_document_signature_payload,
    build_document_signature_token,
    build_document_signature_url,
    build_signature_fields,
    build_signature_signatory_and_observers,
    parse_document_signature_token,
)


logger = logging.getLogger(__name__)

DeliveryChannel = Literal["EMAIL", "WHATSAPP", "BOTH"]


def _phone_digits_for_synplaisign(raw_phone: object) -> str:
    """SynplaiSign expects international digits without '+' (e.g. 5511999999999)."""
    digits = re.sub(r"\D", "", str(raw_phone or ""))
    return digits


def _resolve_delivery_channel(*, phone_digits: str, explicit: object = None) -> DeliveryChannel:
    channels: dict[str, DeliveryChannel] = {
        "EMAIL": "EMAIL",
        "WHATSAPP": "WHATSAPP",
        "BOTH": "BOTH",
    }
    if isinstance(explicit, str):
        resolved = channels.get(explicit.strip().upper())
        if resolved is not None:
            return resolved
    return "BOTH" if phone_digits else "EMAIL"


def _map_signatories(
    *,
    signatory: dict[str, Any],
    fields: list[dict[str, Any]],
    include_field_coords: bool = True,
) -> list[dict[str, Any]]:
    order_raw = signatory.get("signingOrder", signatory.get("order", 0))
    try:
        order = int(order_raw)
    except (TypeError, ValueError):
        order = 0
    if order < 0:
        order = 0

    phone_digits = _phone_digits_for_synplaisign(signatory.get("phone") or signatory.get("phoneNumber"))
    delivery_channel = _resolve_delivery_channel(
        phone_digits=phone_digits,
        explicit=signatory.get("deliveryChannel"),
    )

    mapped: dict[str, Any] = {
        "name": str(signatory.get("name") or "").strip(),
        "email": str(signatory.get("email") or "").strip(),
        "order": order,
        "deliveryChannel": delivery_channel,
    }
    if phone_digits:
        mapped["phone"] = phone_digits

    if not include_field_coords:
        return [mapped]

    field = fields[0] if fields else None
    position = SIGNATURE_POSITION
    page_number = 1
    if isinstance(field, dict):
        page_raw = field.get("pageNumber") or field.get("fieldPage") or 1
        try:
            page_number = int(page_raw)
        except (TypeError, ValueError):
            page_number = 1
        field_position = field.get("position")
        if isinstance(field_position, dict):
            position = field_position

    mapped["fieldPage"] = max(page_number, 1)
    mapped["fieldX"] = float(position.get("x", SIGNATURE_POSITION["x"]))
    mapped["fieldY"] = float(position.get("y", SIGNATURE_POSITION["y"]))
    mapped["fieldWidth"] = float(position.get("width", SIGNATURE_POSITION["width"]))
    mapped["fieldHeight"] = float(position.get("height", SIGNATURE_POSITION["height"]))
    return [mapped]


def _is_html_content_type(content_type: str) -> bool:
    return "html" in str(content_type or "").lower()


def _require_request_api_key(api_key: str) -> str:
    normalized = str(api_key or "").strip()
    if not normalized:
        raise SignatureServiceError("API key SynplaiSign da oficina nao informada")
    return normalized


class SynplaiSignSignatureService(ISignatureService):
    def send_document(self, request: SignatureSendRequest) -> SignatureSendResult:
        api_key = _require_request_api_key(request.api_key)
        include_field_coords = not _is_html_content_type(request.content_type)
        signatories = _map_signatories(
            signatory=request.signatory,
            fields=request.fields,
            include_field_coords=include_field_coords,
        )
        try:
            created = gateway.create_envelope(
                api_key=api_key,
                document_bytes=request.document_bytes,
                file_name=request.file_name,
                title=request.title,
                message=request.message,
                signatories=signatories,
                whatsapp_instance=request.whatsapp_instance,
                content_type=request.content_type,
                sender_name=request.sender_name,
            )
            gateway.send_envelope(api_key=api_key, envelope_id=created.envelope_id)
            signing_url = ""
            if created.signing_token:
                signing_url = gateway.build_signing_url(token=created.signing_token)
        except gateway.SynplaiSignGatewayError as exc:
            raise SignatureServiceError(str(exc)) from exc

        return SignatureSendResult(
            envelope_id=created.envelope_id,
            document_id=created.envelope_id,
            provider="synplaisign",
            raw_response=created.raw_response,
            signing_url=signing_url,
        )

    def get_signed_document_url(self, *, document_id: str, api_key: str = "") -> str:
        try:
            return gateway.get_signed_document_download_url(
                api_key=_require_request_api_key(api_key),
                envelope_id=document_id,
            )
        except gateway.SynplaiSignGatewayError as exc:
            raise SignatureServiceError(str(exc)) from exc

    def download_signed_document(self, *, document_id: str | None = None, envelope_id: str | None = None, api_key: str = "") -> bytes:
        resolved_envelope_id = str(envelope_id or document_id or "").strip()
        if not resolved_envelope_id:
            raise SignatureServiceError("Nenhum identificador do documento assinado foi informado")
        try:
            return gateway.download_signed_document(
                api_key=_require_request_api_key(api_key),
                envelope_id=resolved_envelope_id,
            )
        except gateway.SynplaiSignGatewayError as exc:
            raise SignatureServiceError(str(exc)) from exc

    def list_webhooks(self, *, api_key: str = "") -> list[dict[str, Any]]:
        try:
            return gateway.list_webhooks(api_key=_require_request_api_key(api_key))
        except gateway.SynplaiSignGatewayError as exc:
            raise SignatureServiceError(str(exc)) from exc

    def create_webhook(self, *, url: str, events: list[str] | None = None, is_active: bool = True, api_key: str = "") -> dict[str, Any]:
        del is_active
        try:
            return gateway.create_webhook(api_key=_require_request_api_key(api_key), url=url, events=events)
        except gateway.SynplaiSignGatewayError as exc:
            raise SignatureServiceError(str(exc)) from exc

    def ensure_webhook(self, *, webhook_url: str, events: list[str] | None = None, api_key: str = "") -> dict[str, Any]:
        expected_events = list(events or ["ENVELOPE_COMPLETED", "DOCUMENT_SIGNED", "DOCUMENT_DECLINED"])
        resolved_api_key = _require_request_api_key(api_key)
        try:
            existing = gateway.list_webhooks(api_key=resolved_api_key)
        except gateway.SynplaiSignGatewayError as exc:
            raise SignatureServiceError(str(exc)) from exc

        for webhook in existing:
            webhook_events = webhook.get("events")
            if webhook.get("url") == webhook_url and isinstance(webhook_events, list) and all(event in webhook_events for event in expected_events):
                return webhook

        try:
            created = gateway.create_webhook(api_key=resolved_api_key, url=webhook_url, events=expected_events)
        except gateway.SynplaiSignGatewayError as exc:
            raise SignatureServiceError(str(exc)) from exc

        secret = created.get("secret")
        if isinstance(secret, str) and secret.strip():
            logger.warning(
                "synplaisign_webhook_secret_issued",
                extra={"webhook_id": created.get("id"), "url": webhook_url},
            )
        return created

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
        result = parse_document_signature_token(
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
