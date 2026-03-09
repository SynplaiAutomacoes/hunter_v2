from __future__ import annotations

from django.template.loader import render_to_string

from apps.core.documents.contract import DocumentPayload, DocumentRenderRequest
from apps.core.pdf_playwright import render_pdf_from_html


def render_template_request_to_pdf(render_request: DocumentRenderRequest) -> DocumentPayload:
    html = render_to_string(render_request.template_name, render_request.context)
    pdf_bytes = render_pdf_from_html(html)

    return DocumentPayload(
        content=pdf_bytes,
        filename=render_request.filename,
        content_type=render_request.content_type,
    )
