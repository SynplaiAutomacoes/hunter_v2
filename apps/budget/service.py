from django.conf import settings

from apps.budget.documents.provider import render_budget_pdf_document
from apps.core.domain.contracts.documents import SignatureDeliveryResult, SignatureRecipient
from apps.core.infrastructure.services.signature import (
    build_document_signature_payload,
    build_signature_fields,
    build_signature_signatory_and_observers,
)
from apps.core.infrastructure.services import build_document_signature_url
from apps.core.infrastructure.services.signature import (
    SignatureDeliveryServiceError,
    send_document_for_signature,
)


BUDGET_SIGNATURE_TOKEN_SALT = "budget-signature-file"
BUDGET_SIGNATURE_DOCUMENT_ID_KEY = "budget_id"
BUDGET_SIGNATURE_FILE_ROUTE = "budget:signature_file"
BUDGET_SIGNATURE_PREVIEW_ROUTE = "budget:signature_preview"


def build_signature_payload(budget) -> dict:
    return build_document_signature_payload(
        document_id_key=BUDGET_SIGNATURE_DOCUMENT_ID_KEY,
        document_id=budget.id,
        version=budget.signature_token_version,
    )


def build_signature_file_url(*, budget, request=None) -> str:
    return build_document_signature_url(
        route_name=BUDGET_SIGNATURE_FILE_ROUTE,
        token_salt=BUDGET_SIGNATURE_TOKEN_SALT,
        document_id_key=BUDGET_SIGNATURE_DOCUMENT_ID_KEY,
        document_id=budget.id,
        version=budget.signature_token_version,
        request=request,
    )


def build_signature_preview_url(*, budget, request=None) -> str:
    return build_document_signature_url(
        route_name=BUDGET_SIGNATURE_PREVIEW_ROUTE,
        token_salt=BUDGET_SIGNATURE_TOKEN_SALT,
        document_id_key=BUDGET_SIGNATURE_DOCUMENT_ID_KEY,
        document_id=budget.id,
        version=budget.signature_token_version,
        request=request,
    )


class SuperSignError(Exception):
    pass


def _calculate_pdf_total_pages(budget) -> int:
    return 1


def _build_signature_fields(budget) -> list[dict]:
    return build_signature_fields(
        document_ref_id=f"budget-{budget.id}",
        signatory_ref_id=f"customer-{budget.id}",
        page_number=_calculate_pdf_total_pages(budget),
    )


def _build_budget_pdf_bytes(*, budget, request=None) -> bytes:
    try:
        return render_budget_pdf_document(budget=budget, request=request).content
    except Exception as exc:
        raise SuperSignError(f"Erro ao gerar PDF para assinatura via Playwright: {exc}") from exc


def send_budget_for_signature(*, budget, request=None) -> SignatureDeliveryResult:
    customer_email = getattr(budget.customer, "email", "") if budget.customer else ""
    customer_phone = getattr(budget.customer, "phone", "") if budget.customer else ""

    if not budget.service_expected_completion_at:
        raise SuperSignError("Não é possível enviar para assinatura antes de definir a data prevista de término do serviço.")

    if not budget.customer:
        raise SuperSignError("Orçamento sem cliente vinculado para assinatura")

    if not customer_email:
        raise SuperSignError("Cliente sem email para assinatura")

    signatory, observers = build_signature_signatory_and_observers(
        signatory_id=f"customer-{budget.id}",
        recipient=SignatureRecipient(
            name=budget.customer.name,
            email=customer_email,
            phone=customer_phone,
        ),
    )

    pdf_bytes = _build_budget_pdf_bytes(budget=budget, request=request)
    file_name = f"orcamento-{budget.id}.pdf"

    try:
        result = send_document_for_signature(
            pdf_bytes=pdf_bytes,
            file_name=file_name,
            document_ref_id=f"budget-{budget.id}",
            title=f"Orcamento #{budget.id}",
            message="Segue orcamento para assinatura.",
            signatory=signatory,
            observers=observers,
            fields=_build_signature_fields(budget),
            folder_id=getattr(settings, "SUPERSIGN_FOLDER_ID", ""),
        )
    except SignatureDeliveryServiceError as exc:
        raise SuperSignError(str(exc)) from exc

    return result
