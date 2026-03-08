from __future__ import annotations

from apps.budget.documents.provider import render_budget_pdf_document
from apps.core.documents.contract import DocumentPayload
from apps.workorder.models import WorkOrder


def render_workorder_pdf_document(*, workorder: WorkOrder, request=None, filename: str | None = None) -> DocumentPayload:
    resolved_filename = filename or f"orcamento_{workorder.budget_id}.pdf"
    return render_budget_pdf_document(
        budget=workorder.budget,
        request=request,
        filename=resolved_filename,
    )
