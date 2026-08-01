from __future__ import annotations

from dataclasses import dataclass
import logging

import requests

from apps.core.observability import observe_dependency_call
from apps.core.infrastructure.services.webmania.webmania_auth import WebmaniaAuthError, build_webmania_headers
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message


logger = logging.getLogger(__name__)


class WebmaniaDocumentDownloadError(Exception):
    pass


@dataclass(frozen=True)
class DownloadedWebmaniaDocument:
    content: bytes
    content_type: str
    content_disposition: str


def download_webmania_document(*, workshop, url: str) -> DownloadedWebmaniaDocument:
    normalized_url = str(url or "").strip()
    if not normalized_url:
        raise WebmaniaDocumentDownloadError("O documento ainda não está disponível para download.")

    try:
        headers = build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise WebmaniaDocumentDownloadError(str(exc)) from exc

    try:
        with observe_dependency_call(
            logger=logger,
            dependency_type="http",
            dependency_name="webmania",
            operation="download_document",
            log_context={"url": normalized_url},
        ) as dependency_call:
            response = requests.get(normalized_url, headers=headers, timeout=60)
            dependency_call.set_http_status_code(response.status_code)
            response.raise_for_status()
            dependency_call.success(extra={"content_type": str(response.headers.get("Content-Type") or "application/octet-stream")})
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao baixar documento fiscal")
        raise WebmaniaDocumentDownloadError(message) from exc

    return DownloadedWebmaniaDocument(
        content=response.content,
        content_type=str(response.headers.get("Content-Type") or "application/octet-stream"),
        content_disposition=str(response.headers.get("Content-Disposition") or ""),
    )
