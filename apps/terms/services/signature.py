from __future__ import annotations

from apps.core.domain.contracts.documents import SignatureRecipient
from apps.core.domain.contracts.signature import SignatureSendRequest, SignatureSendResult, SignatureServiceError
from apps.core.infrastructure.providers import get_signature_service
from apps.terms.documents import render_term_signature_html_bytes
from apps.terms.models import TermSource
from apps.workshops.services.synplaisign import WorkshopSynplaiSignError, get_workshop_synplaisign_api_key


class TermSignatureError(Exception):
    pass


def send_term_for_signature(*, budget, template, request=None) -> SignatureSendResult:
    if template.source != TermSource.HTML:
        raise TermSignatureError("Somente termos em texto podem ser enviados para assinatura.")
    topics_manager = getattr(template, "topics", None)
    if hasattr(topics_manager, "filter") and not template.can_send_for_signature:
        raise TermSignatureError("O termo não possui conteúdo para assinatura.")
    if not budget.customer:
        raise TermSignatureError("Orçamento sem cliente vinculado para assinatura.")
    if not budget.vehicle:
        raise TermSignatureError("Orçamento sem veículo vinculado para assinatura.")

    customer_email = getattr(budget.customer, "email", "") or ""
    customer_phone = getattr(budget.customer, "phone", "") or ""
    if not customer_email:
        raise TermSignatureError("Cliente sem email para assinatura.")

    signatory, observers = get_signature_service().build_signatory_and_observers(
        signatory_id=f"term-customer-{budget.id}-{template.id}",
        recipient=SignatureRecipient(
            name=budget.customer.name,
            email=customer_email,
            phone=customer_phone,
        ),
    )

    try:
        document_bytes = render_term_signature_html_bytes(template=template, budget=budget, request=request)
    except Exception as exc:
        raise TermSignatureError(f"Erro ao gerar HTML para assinatura: {exc}") from exc

    try:
        api_key = get_workshop_synplaisign_api_key(budget.workshop)
    except WorkshopSynplaiSignError as exc:
        raise TermSignatureError(str(exc)) from exc

    whatsapp_instance = str(getattr(budget.workshop, "whatsapp_instance_name", "") or "").strip()

    try:
        return get_signature_service().send_document(
            SignatureSendRequest(
                document_bytes=document_bytes,
                file_name=f"termo-{template.id}-orcamento-{budget.id}.html",
                document_ref_id=f"term-{template.id}-budget-{budget.id}",
                title=f"{template.name} #{budget.number}",
                message=f"Segue {template.name} para assinatura.",
                signatory=signatory,
                observers=observers,
                fields=[],
                api_key=api_key,
                whatsapp_instance=whatsapp_instance,
                content_type="text/html",
            )
        )
    except SignatureServiceError as exc:
        raise TermSignatureError(str(exc)) from exc
