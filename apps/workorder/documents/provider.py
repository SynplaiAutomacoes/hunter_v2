from __future__ import annotations

from apps.core.domain.contracts.documents import DocumentPayload, DocumentRenderRequest
from apps.core.infrastructure.pdf.renderer import render_template_request_to_html, render_template_request_to_pdf
from apps.workorder.models import WorkOrder
from apps.workorder.pdf_context import build_workorder_pdf_context


def build_workorder_pdf_render_request(*, workorder: WorkOrder, request=None, filename: str | None = None) -> DocumentRenderRequest:
    resolved_filename = filename or f"ordem_servico_{workorder.get_id}.pdf"
    context = build_workorder_pdf_context(
        workorder=workorder,
        request=request,
    )
    return DocumentRenderRequest(
        template_name="workorder/partials/pdf/visualizarPDF.html",
        context=context,
        filename=resolved_filename,
    )


def build_workorder_signature_html_render_request(*, workorder: WorkOrder, request=None, filename: str | None = None) -> DocumentRenderRequest:
    resolved_filename = filename or f"ordem_servico_{workorder.get_id}.html"
    context = build_workorder_pdf_context(
        workorder=workorder,
        request=request,
    )
    return DocumentRenderRequest(
        template_name="workorder/partials/pdf/visualizarPDF.html",
        context=context,
        filename=resolved_filename,
        content_type="text/html; charset=utf-8",
    )


def render_workorder_pdf_document(*, workorder: WorkOrder, request=None, filename: str | None = None) -> DocumentPayload:
    render_request = build_workorder_pdf_render_request(
        workorder=workorder,
        request=request,
        filename=filename,
    )
    return render_template_request_to_pdf(render_request)


def render_workorder_signature_html_document(*, workorder: WorkOrder, request=None, filename: str | None = None) -> DocumentPayload:
    render_request = build_workorder_signature_html_render_request(
        workorder=workorder,
        request=request,
        filename=filename,
    )
    return render_template_request_to_html(render_request)


def build_workorder_status_report_pdf_render_request(*, context: dict[str, object], request=None, filename: str | None = None) -> DocumentRenderRequest:
    resolved_filename = filename or "relatorio_ordens_servico_filtradas.pdf"
    render_context = dict(context)
    render_context["request"] = request

    return DocumentRenderRequest(
        template_name="workorder/pdf/visualizar_status_report_pdf.html",
        context=render_context,
        filename=resolved_filename,
    )


def render_workorder_status_report_pdf_document(*, context: dict[str, object], request=None, filename: str | None = None) -> DocumentPayload:
    render_request = build_workorder_status_report_pdf_render_request(
        context=context,
        request=request,
        filename=filename,
    )
    return render_template_request_to_pdf(render_request)
