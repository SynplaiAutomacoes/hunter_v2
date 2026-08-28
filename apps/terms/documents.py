from __future__ import annotations

from django.http import HttpRequest
from django.template.loader import render_to_string

from apps.budget.pdf_context import resolve_workshop_logo_src
from apps.terms.content import DEFAULT_CLOSING_TEXT
from apps.terms.models import TERM_DEFAULT_ACCENT_COLOR, TERM_DEFAULT_PRIMARY_COLOR, TermKind
from apps.terms.placeholders import merge_term_placeholders


def _merged(text: str, *, budget) -> str:
    return merge_term_placeholders(text, budget=budget)


def build_term_document_context(*, template, budget=None, request: HttpRequest | None = None) -> dict:
    workshop = getattr(budget, "workshop", None) or getattr(template, "workshop", None)
    topics = []
    topic_queryset = template.topics.prefetch_related("bullets").all()
    for index, topic in enumerate(topic_queryset, start=1):
        topics.append(
            {
                "number": f"{index:02d}",
                "title": _merged(topic.title, budget=budget),
                "items": [_merged(bullet.text, budget=budget) for bullet in topic.bullets.all()],
            }
        )
    kind = getattr(template, "kind", TermKind.RECEIPT)
    if kind == TermKind.RECEIPT:
        title_line1 = "Termo de recebimento"
        title_line2 = "de veículo"
    elif kind == TermKind.WARRANTY:
        title_line1 = "Termo de garantia"
        title_line2 = ""
    else:
        title_line1 = template.name
        title_line2 = ""
    logo = ""
    if workshop is not None:
        logo = resolve_workshop_logo_src(workshop=workshop, request=request)
    primary_color = str(getattr(template, "primary_color", "") or TERM_DEFAULT_PRIMARY_COLOR)
    accent_color = str(getattr(template, "accent_color", "") or TERM_DEFAULT_ACCENT_COLOR)
    return {
        "term_name": template.name,
        "document_kind_label": template.get_kind_display(),
        "document_title_line1": title_line1,
        "document_title_line2": title_line2,
        "workshop_logo_data_uri": logo,
        "primary_color": primary_color,
        "accent_color": accent_color,
        "workshop": workshop,
        "budget": budget,
        "intro_text": _merged(template.intro_text, budget=budget),
        "closing_text": _merged(DEFAULT_CLOSING_TEXT, budget=budget),
        "topics": topics,
        "vehicle_label": _merged("{{vehicle}}", budget=budget),
        "plate_label": _merged("{{plate}}", budget=budget),
        "customer_name": _merged("{{customer_name}}", budget=budget),
        "customer_cpf": _merged("{{customer_cpf}}", budget=budget),
    }


def render_term_signature_html(*, template, budget=None, request: HttpRequest | None = None) -> str:
    return render_to_string(
        "terms/pdf/term_signature.html",
        build_term_document_context(template=template, budget=budget, request=request),
        request=request,
    )


def render_term_signature_html_bytes(*, template, budget=None, request: HttpRequest | None = None) -> bytes:
    return render_term_signature_html(template=template, budget=budget, request=request).encode("utf-8")
