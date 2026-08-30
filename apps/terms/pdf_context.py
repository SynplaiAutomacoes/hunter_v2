from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.budget.pdf_context import build_workshop_logo_data_uri
from apps.terms.models import WorkshopTermTemplate
from apps.terms.services.color_contrast import colors_to_context, extract_sections_from_content, resolve_term_colors


def _resolve_template_data(*, term_template: WorkshopTermTemplate | None, snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if snapshot:
        return snapshot
    if term_template is None:
        return {}
    return {
        "document_title": term_template.document_title,
        "subtitle": term_template.subtitle,
        "intro_text": term_template.intro_text,
        "primary_color": term_template.primary_color,
        "accent_color": term_template.accent_color,
        "text_color": term_template.text_color,
        "muted_color": term_template.muted_color,
        "content": term_template.content,
    }


def _build_vehicle_display(vehicle) -> tuple[str, str]:
    if vehicle is None:
        return "", ""
    brand = str(getattr(vehicle, "brand", "") or "").strip()
    model = str(getattr(vehicle, "model", "") or "").strip()
    plate = str(getattr(vehicle, "plate", "") or "").strip()
    if brand and model:
        vehicle_display = f"{brand} / {model}"
    else:
        vehicle_display = brand or model
    return vehicle_display.upper(), plate.upper()


def build_term_pdf_context(
    *,
    term_template: WorkshopTermTemplate | None = None,
    snapshot: dict[str, Any] | None = None,
    workshop,
    customer=None,
    vehicle=None,
    acknowledgment_text: str | None = None,
    warranty_plan_display: str | None = None,
) -> dict[str, Any]:
    data = _resolve_template_data(term_template=term_template, snapshot=snapshot)
    colors = resolve_term_colors(
        primary=str(data.get("primary_color") or "#000000"),
        accent=str(data.get("accent_color") or "#E30613"),
        text=str(data.get("text_color") or "#111827"),
        muted=str(data.get("muted_color") or "#6B7280"),
    )
    content = data.get("content") if isinstance(data.get("content"), dict) else {}
    sections = extract_sections_from_content(content)

    workshop_name = getattr(workshop, "nome_fantasia_display", None) or getattr(workshop, "name", "") or ""
    vehicle_display, vehicle_plate_display = _build_vehicle_display(vehicle)
    generated_at = timezone.localtime()

    return {
        "document_title": data.get("document_title") or "TERMO",
        "subtitle": data.get("subtitle") or "",
        "intro_text": data.get("intro_text") or "",
        "acknowledgment_text": acknowledgment_text
        or "Declaro que li, compreendi e concordo com as condições apresentadas neste Termo de Recebimento de Veículo.",
        "sections": sections,
        "colors": colors_to_context(colors),
        "workshop_logo_data_uri": build_workshop_logo_data_uri(workshop=workshop),
        "workshop": workshop,
        "workshop_name": workshop_name,
        "customer": customer,
        "vehicle": vehicle,
        "vehicle_display": vehicle_display,
        "vehicle_plate_display": vehicle_plate_display,
        "warranty_plan_display": warranty_plan_display or "",
        "generated_at": generated_at,
    }
