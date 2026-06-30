from __future__ import annotations

from django.http import HttpResponse
from django.template.loader import render_to_string

from apps.core.domain import DocumentPayload
from apps.core.domain.contracts.documents import DocumentPayload, DocumentRenderRequest
from apps.core.infrastructure.pdf.pdf_engine import render_pdf_from_html


def render_template_request_to_pdf(render_request: DocumentRenderRequest) -> DocumentPayload:
    html = render_to_string(render_request.template_name, render_request.context)
    pdf_bytes = render_pdf_from_html(html)

    return DocumentPayload(
        content=pdf_bytes,
        filename=render_request.filename,
        content_type=render_request.content_type,
    )


def build_pdf_http_response(*, document: DocumentPayload, download: bool = False) -> HttpResponse:
    disposition = "attachment" if download else "inline"

    response = HttpResponse(document.content, content_type=document.content_type)
    response["Content-Disposition"] = f'{disposition}; filename="{document.filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store"
    return response
