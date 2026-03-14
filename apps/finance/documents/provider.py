from __future__ import annotations

import re
import unicodedata

from apps.core.documents.contract import DocumentPayload, DocumentRenderRequest
from apps.core.documents.renderer import render_template_request_to_pdf
from apps.workshops.models.workshops import Workshop


def build_dre_pdf_render_request(*, context: dict[str, object], request=None, filename: str | None = None) -> DocumentRenderRequest:
    selected_workshop = context.get("selected_workshop")
    workshop = selected_workshop if isinstance(selected_workshop, Workshop) else None
    data_inicial_label = str(context.get("data_inicial_label") or "-")
    data_final_label = str(context.get("data_final_label") or "-")
    resolved_filename = filename or _build_filename(
        workshop=workshop,
        data_inicial_label=data_inicial_label,
        data_final_label=data_final_label,
    )

    render_context = dict(context)
    render_context["request"] = request

    return DocumentRenderRequest(
        template_name="finance/dre/pdf/visualizarPDF.html",
        context=render_context,
        filename=resolved_filename,
    )


def render_dre_pdf_document(*, context: dict[str, object], request=None, filename: str | None = None) -> DocumentPayload:
    render_request = build_dre_pdf_render_request(context=context, request=request, filename=filename)
    return render_template_request_to_pdf(render_request)


def _build_filename(*, workshop: Workshop | None, data_inicial_label: str, data_final_label: str) -> str:
    workshop_fragment = _normalize_filename_fragment(workshop.name) if workshop is not None else "consolidado"
    start_fragment = _normalize_filename_fragment(data_inicial_label)
    end_fragment = _normalize_filename_fragment(data_final_label)
    return f"dre_{workshop_fragment}_{start_fragment}_{end_fragment}.pdf"


def _normalize_filename_fragment(value: str) -> str:
    normalized_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized_value = normalized_value.lower().strip()
    normalized_value = re.sub(r"[^a-z0-9]+", "_", normalized_value)
    normalized_value = normalized_value.strip("_")
    return normalized_value or "-"
