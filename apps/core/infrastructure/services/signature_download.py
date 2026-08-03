"""Route signed-PDF download: SynplaiSign first, SuperSign fallback for legacy docs."""

from __future__ import annotations

import logging

from apps.core.domain.contracts.signature import SignatureServiceError
from apps.core.infrastructure.gateways import supersign as supersign_gateway
from apps.core.infrastructure.providers import get_signature_service


logger = logging.getLogger(__name__)


def _resolve_supersign_document_id(*, document_id: str | None, envelope_id: str | None) -> str:
    resolved_doc = str(document_id or "").strip()
    if resolved_doc:
        return resolved_doc

    resolved_envelope = str(envelope_id or "").strip()
    if not resolved_envelope:
        raise SignatureServiceError("Nenhum identificador do documento assinado foi informado para SuperSign")

    return supersign_gateway.get_supersign_envelope_signed_document_id(envelope_id=resolved_envelope)


def download_signed_pdf(
    *,
    document_id: str | None = None,
    envelope_id: str | None = None,
    synplaisign_api_key: str = "",
) -> bytes:
    synplaisign_error: Exception | None = None
    try:
        logger.info(
            "signature_download_via_synplaisign",
            extra={"document_id": document_id, "envelope_id": envelope_id},
        )
        return get_signature_service().download_signed_document(
            document_id=document_id,
            envelope_id=envelope_id,
            api_key=synplaisign_api_key,
        )
    except SignatureServiceError as exc:
        synplaisign_error = exc
        logger.warning(
            "signature_download_synplaisign_failed_fallback_supersign",
            extra={
                "document_id": document_id,
                "envelope_id": envelope_id,
                "error": str(exc),
            },
        )

    try:
        resolved_doc = _resolve_supersign_document_id(document_id=document_id, envelope_id=envelope_id)
        logger.info(
            "signature_download_via_supersign",
            extra={"document_id": resolved_doc, "envelope_id": envelope_id},
        )
        return supersign_gateway.download_signed_document(document_id=resolved_doc)
    except supersign_gateway.SuperSignGatewayError as exc:
        message = str(exc)
        if synplaisign_error is not None:
            message = f"{synplaisign_error}; SuperSign fallback: {exc}"
        raise SignatureServiceError(message) from exc
