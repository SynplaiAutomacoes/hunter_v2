from __future__ import annotations

from django.http import HttpResponse

from apps.core.documents.contract import DocumentPayload


def build_pdf_http_response(*, document: DocumentPayload, download: bool = False) -> HttpResponse:
    disposition = "attachment" if download else "inline"

    response = HttpResponse(document.content, content_type=document.content_type)
    response["Content-Disposition"] = f'{disposition}; filename="{document.filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store"
    return response
