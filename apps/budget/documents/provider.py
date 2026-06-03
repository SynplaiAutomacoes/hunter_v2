from __future__ import annotations

from apps.budget.pdf_context import build_budget_pdf_context
from apps.core.documents.contract import DocumentPayload, DocumentRenderRequest
from apps.core.documents.renderer import render_template_request_to_pdf


def build_budget_pdf_render_request(*, budget, request=None, filename: str | None = None) -> DocumentRenderRequest:
    context = build_budget_pdf_context(budget=budget, request=request, zero_warranty_prices=True, presentation="selected_items")
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
    resolved_filename = filename or "relatorio_orcamentos_filtrados.pdf"
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
