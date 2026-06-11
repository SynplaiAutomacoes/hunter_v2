from __future__ import annotations

from dataclasses import dataclass

import requests

from apps.core.infrastructure.services.webmania.webmania_auth import WebmaniaAuthError, build_webmania_headers
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message


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
        raise WebmaniaDocumentDownloadError("O documento ainda nao esta disponivel para download.")

    try:
        headers = build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise WebmaniaDocumentDownloadError(str(exc)) from exc

    try:
        response = requests.get(normalized_url, headers=headers, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao baixar documento fiscal")
        raise WebmaniaDocumentDownloadError(message) from exc

    return DownloadedWebmaniaDocument(
        content=response.content,
        content_type=str(response.headers.get("Content-Type") or "application/octet-stream"),
        content_disposition=str(response.headers.get("Content-Disposition") or ""),
    )
