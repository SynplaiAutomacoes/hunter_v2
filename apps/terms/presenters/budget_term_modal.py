from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse

from apps.budget.models import SignatureStatus
from apps.terms.models import BudgetTermSigning
from apps.terms.services.signature import build_budget_term_signature_file_url


@dataclass(frozen=True, slots=True)
class BudgetTermModalUrls:
    can_toggle_signed_pdf: bool
    is_signature_resend: bool
    signature_blocked: bool
    initial_pdf_variant: str
    initial_pdf_url: str
    initial_download_url: str
    signed_pdf_url: str
    base_pdf_url: str
    signed_download_url: str
    base_download_url: str


def _build_base_pdf_urls(*, budget_id: int, term_template_id: int | None) -> tuple[str, str]:
    base_path = reverse("terms:budget_term_pdf", kwargs={"budget_id": budget_id})
    if term_template_id:
        query = f"term_template={term_template_id}"
        return f"{base_path}?{query}", f"{base_path}?download=1&{query}"
    return base_path, f"{base_path}?download=1"


def resolve_budget_term_modal_urls(
    *,
    budget_id: int,
    signing: BudgetTermSigning | None,
    term_template_id: int | None,
    request=None,
) -> BudgetTermModalUrls:
    base_pdf_url, base_download_url = _build_base_pdf_urls(budget_id=budget_id, term_template_id=term_template_id)
    can_toggle_signed_pdf = bool(
        signing
        and signing.signature_request_status in {SignatureStatus.SENT, SignatureStatus.APPROVED}
        and signing.signature_token_active
    )
    is_signature_resend = bool(
        signing and signing.signature_request_status == SignatureStatus.SENT and signing.signature_external_id
    )
    signature_blocked = bool(
        signing and signing.signature_request_status in {SignatureStatus.APPROVED, SignatureStatus.SENDING}
    )

    signed_pdf_url = ""
    signed_download_url = ""
    if signing and can_toggle_signed_pdf:
        signed_pdf_url = build_budget_term_signature_file_url(signing=signing, request=request)
        signed_download_url = f"{signed_pdf_url}?download=1"

    if can_toggle_signed_pdf:
        initial_pdf_variant = "signed"
        initial_pdf_url = signed_pdf_url or base_pdf_url
        initial_download_url = signed_download_url or base_download_url
    else:
        initial_pdf_variant = "base"
        initial_pdf_url = base_pdf_url
        initial_download_url = base_download_url

    return BudgetTermModalUrls(
        can_toggle_signed_pdf=can_toggle_signed_pdf,
        is_signature_resend=is_signature_resend,
        signature_blocked=signature_blocked,
        initial_pdf_variant=initial_pdf_variant,
        initial_pdf_url=initial_pdf_url,
        initial_download_url=initial_download_url,
        signed_pdf_url=signed_pdf_url,
        base_pdf_url=base_pdf_url,
        signed_download_url=signed_download_url,
        base_download_url=base_download_url,
    )
