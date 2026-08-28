from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from django.http import QueryDict
from django.urls import reverse

from apps.terms.models import BudgetTermSigning, TermSignatureStatus


def new_topic_key() -> str:
    return uuid.uuid4().hex[:12]


_TERM_SIGNATURE_STATUS_BADGES: dict[str, tuple[str, str]] = {
    TermSignatureStatus.NOT_SENT: ("Não enviado", "badge-ghost"),
    TermSignatureStatus.SENDING: ("Enviando", "badge-info"),
    TermSignatureStatus.SENT: ("Enviado", "badge-warning"),
    TermSignatureStatus.FAILED: ("Falha no envio", "badge-error"),
    TermSignatureStatus.APPROVED: ("Assinado", "badge-success"),
    TermSignatureStatus.DECLINED: ("Recusado", "badge-error"),
}


def term_signature_status_badge(signing: BudgetTermSigning | None) -> dict[str, str]:
    if signing is None:
        return {"text": "Não enviado", "class": "badge-ghost"}
    text, css_class = _TERM_SIGNATURE_STATUS_BADGES.get(signing.signature_request_status, ("Desconhecido", "badge-ghost"))
    return {"text": text, "class": css_class}


def can_toggle_term_signed_pdf(signing: BudgetTermSigning | None) -> bool:
    if signing is None:
        return False
    return signing.signature_request_status in {TermSignatureStatus.SENT, TermSignatureStatus.APPROVED} and bool(
        signing.signature_external_id or signing.signature_document_id
    )


@dataclass(frozen=True, slots=True)
class TermModalUrls:
    can_toggle_signed_pdf: bool
    initial_pdf_variant: str
    default_iframe_url: str
    base_iframe_url: str
    signed_iframe_url: str
    signed_download_url: str


def resolve_term_modal_urls(
    *,
    budget_id: int,
    template_id: int,
    can_toggle_signed_pdf: bool,
    signing: BudgetTermSigning | None = None,
) -> TermModalUrls:
    base_iframe_url = reverse("terms:budget_term_preview", args=[budget_id, template_id])
    signed_iframe_url = reverse("terms:budget_term_signed", args=[budget_id, template_id])
    signed_download_url = f"{signed_iframe_url}?download=1"
    is_approved = signing is not None and signing.signature_request_status == TermSignatureStatus.APPROVED
    if can_toggle_signed_pdf:
        initial_variant = "signed" if is_approved else "base"
        default_url = signed_iframe_url if is_approved else base_iframe_url
        return TermModalUrls(
            can_toggle_signed_pdf=True,
            initial_pdf_variant=initial_variant,
            default_iframe_url=default_url,
            base_iframe_url=base_iframe_url,
            signed_iframe_url=signed_iframe_url,
            signed_download_url=signed_download_url,
        )
    return TermModalUrls(
        can_toggle_signed_pdf=False,
        initial_pdf_variant="base",
        default_iframe_url=base_iframe_url,
        base_iframe_url=base_iframe_url,
        signed_iframe_url=signed_iframe_url,
        signed_download_url=signed_download_url,
    )


def build_term_signing_status_map(*, terms: list[Any], signings_by_template_id: dict[int, BudgetTermSigning]) -> dict[str, dict[str, str]]:
    return {str(term.pk): term_signature_status_badge(signings_by_template_id.get(term.pk)) for term in terms}


def extract_term_sections(post_data: QueryDict) -> list[dict[str, Any]]:
    order = [str(value).strip() for value in post_data.getlist("topic_order") if str(value).strip()]
    if not order:
        keys = [key[len("topic_title_") :] for key in post_data.keys() if str(key).startswith("topic_title_")]
        order = keys

    sections: list[dict[str, Any]] = []
    for key in order:
        title = str(post_data.get(f"topic_title_{key}") or "").strip()
        items = [str(item).strip() for item in post_data.getlist(f"topic_item_{key}") if str(item).strip()]
        if not title and not items:
            continue
        if not title:
            raise ValueError("Informe o título de todos os tópicos.")
        if not items:
            raise ValueError("Cada tópico precisa de pelo menos um texto.")
        sections.append({"key": key, "title": title, "items": items})
    return sections


def build_showtoast_trigger(toast_type: str, message: str) -> str:
    return json.dumps({"showToast": {"type": toast_type, "message": message}})


def build_term_send_success_trigger(*, message: str, status_badge: dict[str, str]) -> str:
    return json.dumps(
        {
            "showToast": {"type": "success", "message": message},
            "closeBudgetTermModal": True,
            "updateReceiptTermStatusBadge": status_badge,
        }
    )
