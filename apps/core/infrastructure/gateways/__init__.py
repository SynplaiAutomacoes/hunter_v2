from apps.core.infrastructure.gateways.supersign import (
    SuperSignGatewayError,
    download_signed_document as download_supersign_signed_document,
    get_signed_document_download_url as get_supersign_signed_document_download_url,
    get_supersign_envelope_signed_document_id,
)
from apps.core.infrastructure.gateways.synplaisign import (
    SynplaiSignGatewayError,
    SynplaiSignGatewayResult,
    build_signing_url,
    create_api_key,
    create_envelope,
    create_webhook,
    delete_webhook,
    download_signed_document,
    get_signed_document_download_url,
    list_webhooks,
    register_with_api_key,
    send_envelope,
)

__all__ = [
    "SuperSignGatewayError",
    "SynplaiSignGatewayError",
    "SynplaiSignGatewayResult",
    "build_signing_url",
    "create_api_key",
    "create_envelope",
    "create_webhook",
    "delete_webhook",
    "download_signed_document",
    "download_supersign_signed_document",
    "get_signed_document_download_url",
    "get_supersign_envelope_signed_document_id",
    "get_supersign_signed_document_download_url",
    "list_webhooks",
    "register_with_api_key",
    "send_envelope",
]
