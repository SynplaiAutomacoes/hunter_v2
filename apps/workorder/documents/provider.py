from __future__ import annotations

from apps.core.documents.contract import DocumentPayload, DocumentRenderRequest
from apps.core.documents.renderer import render_template_request_to_pdf
from apps.workorder.models import WorkOrder
from apps.workorder.pdf_context import build_workorder_pdf_context


def build_workorder_pdf_render_request(*, workorder: WorkOrder, request=None, filename: str | None = None) -> DocumentRenderRequest:
    resolved_filename = filename or f"ordem_servico_{workorder.public_number}.pdf"
    context = build_workorder_pdf_context(
        workorder=workorder,
        observacao=workorder.budget.pdf_observation,
        request=request,
    )
    return DocumentRenderRequest(
        template_name="workorder/partials/pdf/visualizarPDF.html",
        context=context,
        filename=resolved_filename,
    )


def render_workorder_pdf_document(*, workorder: WorkOrder, request=None, filename: str | None = None) -> DocumentPayload:
    render_request = build_workorder_pdf_render_request(
        workorder=workorder,
        request=request,
        filename=filename,
    )
    return render_template_request_to_pdf(render_request)


def build_workorder_status_report_pdf_render_request(*, context: dict[str, object], request=None, filename: str | None = None) -> DocumentRenderRequest:
    selected_status_report = context.get("selected_status_report")
    status_value = "status"
    if isinstance(selected_status_report, dict):
        status_value = str(selected_status_report.get("value") or status_value)

    resolved_filename = filename or f"relatorio_ordens_servico_por_status_{status_value}.pdf"
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
