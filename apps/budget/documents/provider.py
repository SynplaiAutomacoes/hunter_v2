from __future__ import annotations

from apps.budget.pdf_context import build_budget_pdf_context
from apps.core.documents.contract import DocumentPayload, DocumentRenderRequest
from apps.core.documents.renderer import render_template_request_to_pdf


def build_budget_pdf_render_request(*, budget, request=None, filename: str | None = None) -> DocumentRenderRequest:
    context = build_budget_pdf_context(budget=budget, observacao=budget.workshop.pdf_observation, request=request)
    resolved_filename = filename or f"orcamento_{budget.id}.pdf"
    return DocumentRenderRequest(
        template_name="budget/partials/pdf/visualizarPDF.html",
        context=context,
        filename=resolved_filename,
    )


def render_budget_pdf_document(*, budget, request=None, filename: str | None = None) -> DocumentPayload:
    render_request = build_budget_pdf_render_request(budget=budget, request=request, filename=filename)
    return render_template_request_to_pdf(render_request)


def build_budget_status_report_pdf_render_request(*, context: dict[str, object], request=None, filename: str | None = None) -> DocumentRenderRequest:
    selected_status_report = context.get("selected_status_report")
    status_value = "status"
    if isinstance(selected_status_report, dict):
        status_value = str(selected_status_report.get("value") or status_value)

    resolved_filename = filename or f"relatorio_orcamentos_por_status_{status_value}.pdf"
    render_context = dict(context)
    render_context["request"] = request

    return DocumentRenderRequest(
        template_name="budget/pdf/visualizar_status_report_pdf.html",
        context=render_context,
        filename=resolved_filename,
    )


def render_budget_status_report_pdf_document(*, context: dict[str, object], request=None, filename: str | None = None) -> DocumentPayload:
    render_request = build_budget_status_report_pdf_render_request(
        context=context,
        request=request,
        filename=filename,
    )
    return render_template_request_to_pdf(render_request)
