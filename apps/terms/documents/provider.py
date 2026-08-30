from __future__ import annotations

from apps.core.domain.contracts.documents import DocumentPayload, DocumentRenderRequest
from apps.core.infrastructure.pdf.renderer import render_template_request_to_html, render_template_request_to_pdf


def build_term_html_render_request(
    *,
    context: dict,
    filename: str,
) -> DocumentRenderRequest:
    return DocumentRenderRequest(
        template_name="terms/pdf/term_document.html",
        context=context,
        filename=filename,
        content_type="text/html; charset=utf-8",
    )


def build_term_pdf_render_request(
    *,
    context: dict,
    filename: str,
) -> DocumentRenderRequest:
    return DocumentRenderRequest(
        template_name="terms/pdf/term_document.html",
        context=context,
        filename=filename,
    )


def render_term_signature_html_document(*, context: dict, filename: str) -> DocumentPayload:
    render_request = build_term_html_render_request(context=context, filename=filename)
    return render_template_request_to_html(render_request)


def render_term_pdf_document(*, context: dict, filename: str) -> DocumentPayload:
    render_request = build_term_pdf_render_request(context=context, filename=filename)
    return render_template_request_to_pdf(render_request)
