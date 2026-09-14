from __future__ import annotations

from apps.core.domain.contracts.documents import SignatureRecipient
from apps.core.domain.contracts.signature import SignatureSendRequest, SignatureSendResult, SignatureServiceError
from apps.core.infrastructure.providers import get_signature_service
from apps.terms.documents.provider import render_term_signature_html_document
from apps.terms.models import BudgetTermSigning, WorkOrderTermSigning
from apps.terms.pdf_context import build_term_pdf_context
from apps.workshops.services.synplaisign import (
    WorkshopSynplaiSignError,
    _organization_name_for_workshop,
    get_workshop_synplaisign_api_key,
)


BUDGET_TERM_SIGNATURE_TOKEN_SALT = "budget-term-signature-file"
BUDGET_TERM_SIGNATURE_DOCUMENT_ID_KEY = "budget_term_signing_id"
BUDGET_TERM_SIGNATURE_FILE_ROUTE = "terms:budget_term_signature_file"
BUDGET_TERM_SIGNATURE_PREVIEW_ROUTE = "terms:budget_term_signature_preview"

WORKORDER_TERM_SIGNATURE_TOKEN_SALT = "workorder-term-signature-file"
WORKORDER_TERM_SIGNATURE_DOCUMENT_ID_KEY = "workorder_term_signing_id"
WORKORDER_TERM_SIGNATURE_FILE_ROUTE = "terms:workorder_term_signature_file"
WORKORDER_TERM_SIGNATURE_PREVIEW_ROUTE = "terms:workorder_term_signature_preview"


class TermSignatureError(Exception):
    pass


def _build_budget_term_context(*, signing: BudgetTermSigning) -> dict:
    budget = signing.budget
    snapshot = signing.content_snapshot if signing.is_signature_locked and signing.content_snapshot else None
    return build_term_pdf_context(
        term_template=signing.term_template,
        snapshot=snapshot,
        workshop=budget.workshop,
        customer=budget.customer,
        vehicle=budget.vehicle,
    )


def _build_workorder_term_context(*, signing: WorkOrderTermSigning) -> dict:
    workorder = signing.workorder
    budget = workorder.budget
    snapshot = signing.content_snapshot if signing.is_signature_locked and signing.content_snapshot else None
    return build_term_pdf_context(
        term_template=signing.term_template,
        snapshot=snapshot,
        workshop=workorder.workshop,
        customer=budget.customer if budget else None,
        vehicle=budget.vehicle if budget else None,
        warranty_plan_display=getattr(workorder, "warranty_plan_display", "") or "",
    )


def send_budget_term_for_signature(*, signing: BudgetTermSigning) -> SignatureSendResult:
    budget = signing.budget
    customer = budget.customer
    customer_email = getattr(customer, "email", "") if customer else ""
    customer_phone = getattr(customer, "phone", "") if customer else ""

    if not customer:
        raise TermSignatureError("Orçamento sem cliente vinculado para assinatura do termo.")
    if not customer_email:
        raise TermSignatureError("Cliente sem e-mail para assinatura do termo.")

    signing.freeze_snapshot()
    context = _build_budget_term_context(signing=signing)
    document = render_term_signature_html_document(
        context=context,
        filename=f"termo-recebimento-{budget.id}.html",
    )

    signatory, observers = get_signature_service().build_signatory_and_observers(
        signatory_id=f"customer-term-{signing.pk}",
        recipient=SignatureRecipient(
            name=customer.name,
            email=customer_email,
            phone=customer_phone,
        ),
    )

    try:
        api_key = get_workshop_synplaisign_api_key(budget.workshop)
    except WorkshopSynplaiSignError as exc:
        raise TermSignatureError(str(exc)) from exc

    whatsapp_instance = str(getattr(budget.workshop, "whatsapp_instance_name", "") or "").strip()
    sender_name = _organization_name_for_workshop(budget.workshop)

    try:
        return get_signature_service().send_document(
            SignatureSendRequest(
                document_bytes=document.content,
                file_name=f"termo-recebimento-{budget.number}.html",
                document_ref_id=f"budget-term-{signing.pk}",
                title=f"Termo de recebimento #{budget.number}",
                message="Segue termo de recebimento do veículo para assinatura.",
                signatory=signatory,
                observers=observers,
                fields=[],
                api_key=api_key,
                whatsapp_instance=whatsapp_instance,
                content_type="text/html",
                sender_name=sender_name,
            )
        )
    except SignatureServiceError as exc:
        raise TermSignatureError(str(exc)) from exc


def send_workorder_term_for_signature(*, signing: WorkOrderTermSigning) -> SignatureSendResult:
    workorder = signing.workorder
    budget = workorder.budget
    customer = budget.customer if budget else None
    customer_email = getattr(customer, "email", "") if customer else ""
    customer_phone = getattr(customer, "phone", "") if customer else ""

    if not customer:
        raise TermSignatureError("Ordem de serviço sem cliente vinculado para assinatura do termo.")
    if not customer_email:
        raise TermSignatureError("Cliente sem e-mail para assinatura do termo.")

    signing.freeze_snapshot()
    context = _build_workorder_term_context(signing=signing)
    document = render_term_signature_html_document(
        context=context,
        filename=f"termo-garantia-{workorder.id}.html",
    )

    signatory, observers = get_signature_service().build_signatory_and_observers(
        signatory_id=f"customer-warranty-term-{signing.pk}",
        recipient=SignatureRecipient(
            name=customer.name,
            email=customer_email,
            phone=customer_phone,
        ),
    )

    try:
        api_key = get_workshop_synplaisign_api_key(workorder.workshop)
    except WorkshopSynplaiSignError as exc:
        raise TermSignatureError(str(exc)) from exc

    whatsapp_instance = str(getattr(workorder.workshop, "whatsapp_instance_name", "") or "").strip()
    sender_name = _organization_name_for_workshop(workorder.workshop)

    try:
        return get_signature_service().send_document(
            SignatureSendRequest(
                document_bytes=document.content,
                file_name=f"termo-garantia-{workorder.get_id}.html",
                document_ref_id=f"workorder-term-{signing.pk}",
                title=f"Termo de garantia O.S. #{workorder.get_id}",
                message="Segue termo de garantia para assinatura.",
                signatory=signatory,
                observers=observers,
                fields=[],
                api_key=api_key,
                whatsapp_instance=whatsapp_instance,
                content_type="text/html",
                sender_name=sender_name,
            )
        )
    except SignatureServiceError as exc:
        raise TermSignatureError(str(exc)) from exc


def build_budget_term_signature_file_url(*, signing: BudgetTermSigning, request=None) -> str:
    return get_signature_service().build_signature_url(
        route_name=BUDGET_TERM_SIGNATURE_FILE_ROUTE,
        token_salt=BUDGET_TERM_SIGNATURE_TOKEN_SALT,
        document_id_key=BUDGET_TERM_SIGNATURE_DOCUMENT_ID_KEY,
        document_id=signing.pk,
        version=signing.signature_token_version,
        request=request,
    )


def build_budget_term_signature_preview_url(*, signing: BudgetTermSigning, request=None) -> str:
    return get_signature_service().build_signature_url(
        route_name=BUDGET_TERM_SIGNATURE_PREVIEW_ROUTE,
        token_salt=BUDGET_TERM_SIGNATURE_TOKEN_SALT,
        document_id_key=BUDGET_TERM_SIGNATURE_DOCUMENT_ID_KEY,
        document_id=signing.pk,
        version=signing.signature_token_version,
        request=request,
    )


def build_workorder_term_signature_file_url(*, signing: WorkOrderTermSigning, request=None) -> str:
    return get_signature_service().build_signature_url(
        route_name=WORKORDER_TERM_SIGNATURE_FILE_ROUTE,
        token_salt=WORKORDER_TERM_SIGNATURE_TOKEN_SALT,
        document_id_key=WORKORDER_TERM_SIGNATURE_DOCUMENT_ID_KEY,
        document_id=signing.pk,
        version=signing.signature_token_version,
        request=request,
    )


def build_workorder_term_signature_preview_url(*, signing: WorkOrderTermSigning, request=None) -> str:
    return get_signature_service().build_signature_url(
        route_name=WORKORDER_TERM_SIGNATURE_PREVIEW_ROUTE,
        token_salt=WORKORDER_TERM_SIGNATURE_TOKEN_SALT,
        document_id_key=WORKORDER_TERM_SIGNATURE_DOCUMENT_ID_KEY,
        document_id=signing.pk,
        version=signing.signature_token_version,
        request=request,
    )
