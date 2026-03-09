from __future__ import annotations

from apps.budget.documents.provider import build_budget_pdf_render_request
from apps.core.documents.contract import DocumentPayload, DocumentRenderRequest
from apps.core.documents.renderer import render_template_request_to_pdf
from apps.workorder.models import WorkOrder


def build_workorder_pdf_render_request(*, workorder: WorkOrder, request=None, filename: str | None = None) -> DocumentRenderRequest:
    resolved_filename = filename or f"ordem_servico_{workorder.id}.pdf"
    return build_budget_pdf_render_request(
        budget=workorder.budget,
        request=request,
        filename=resolved_filename,
    )


def render_workorder_pdf_document(*, workorder: WorkOrder, request=None, filename: str | None = None) -> DocumentPayload:
    render_request = build_workorder_pdf_render_request(
        workorder=workorder,
        request=request,
        filename=filename,
    )
    return render_template_request_to_pdf(render_request)
