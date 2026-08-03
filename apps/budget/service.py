from apps.budget.documents.provider import render_budget_pdf_document
from apps.core.domain.contracts.documents import SignatureRecipient
from apps.core.domain.contracts.signature import SignatureSendRequest, SignatureSendResult, SignatureServiceError
from apps.core.infrastructure.providers import get_signature_service
from apps.workshops.services.synplaisign import WorkshopSynplaiSignError, get_workshop_synplaisign_api_key


BUDGET_SIGNATURE_TOKEN_SALT = "budget-signature-file"
BUDGET_SIGNATURE_DOCUMENT_ID_KEY = "budget_id"
BUDGET_SIGNATURE_FILE_ROUTE = "budget:signature_file"
BUDGET_SIGNATURE_PREVIEW_ROUTE = "budget:signature_preview"


def can_use_signed_budget_pdf(*, budget) -> bool:
    from apps.budget.models import SignatureStatus

    return bool(budget.signature_document_id or budget.signature_external_id) and budget.signature_request_status in {SignatureStatus.SENT, SignatureStatus.APPROVED}


def should_default_to_signed_budget_pdf(*, budget) -> bool:
    from apps.budget.models import SignatureStatus

    return bool(budget.signature_document_id or budget.signature_external_id) and budget.signature_request_status == SignatureStatus.APPROVED


def build_signature_payload(budget) -> dict:
    return get_signature_service().build_signature_payload(
        document_id_key=BUDGET_SIGNATURE_DOCUMENT_ID_KEY,
        document_id=budget.id,
        version=budget.signature_token_version,
    )


def build_signature_file_url(*, budget, request=None) -> str:
    return get_signature_service().build_signature_url(
        route_name=BUDGET_SIGNATURE_FILE_ROUTE,
        token_salt=BUDGET_SIGNATURE_TOKEN_SALT,
        document_id_key=BUDGET_SIGNATURE_DOCUMENT_ID_KEY,
        document_id=budget.id,
        version=budget.signature_token_version,
        request=request,
    )


def build_signature_preview_url(*, budget, request=None) -> str:
    return get_signature_service().build_signature_url(
        route_name=BUDGET_SIGNATURE_PREVIEW_ROUTE,
        token_salt=BUDGET_SIGNATURE_TOKEN_SALT,
        document_id_key=BUDGET_SIGNATURE_DOCUMENT_ID_KEY,
        document_id=budget.id,
        version=budget.signature_token_version,
        request=request,
    )


class SignatureError(Exception):
    pass


# Backward-compatible alias.
SuperSignError = SignatureError


def _calculate_pdf_total_pages(budget) -> int:
    return 1


def _build_signature_fields(budget) -> list[dict]:
    return get_signature_service().build_signature_fields(
        document_ref_id=f"budget-{budget.id}",
        signatory_ref_id=f"customer-{budget.id}",
        page_number=_calculate_pdf_total_pages(budget),
    )


def _build_budget_pdf_bytes(*, budget, request=None) -> bytes:
    try:
        return render_budget_pdf_document(budget=budget, request=request).content
    except Exception as exc:
        raise SignatureError(f"Erro ao gerar PDF para assinatura via Playwright: {exc}") from exc


def send_budget_for_signature(*, budget, request=None) -> SignatureSendResult:
    customer_email = getattr(budget.customer, "email", "") if budget.customer else ""
    customer_phone = getattr(budget.customer, "phone", "") if budget.customer else ""

    if not budget.service_expected_completion_at:
        raise SignatureError("Não é possível enviar para assinatura antes de definir a data prevista de término do serviço.")

    if not budget.customer:
        raise SignatureError("Orçamento sem cliente vinculado para assinatura")

    if not customer_email:
        raise SignatureError("Cliente sem email para assinatura")

    signatory, observers = get_signature_service().build_signatory_and_observers(
        signatory_id=f"customer-{budget.id}",
        recipient=SignatureRecipient(
            name=budget.customer.name,
            email=customer_email,
            phone=customer_phone,
        ),
    )

    pdf_bytes = _build_budget_pdf_bytes(budget=budget, request=request)
    file_name = f"orcamento-{budget.id}.pdf"
    title = f"Orcamento #{budget.id}"

    try:
        api_key = get_workshop_synplaisign_api_key(budget.workshop)
    except WorkshopSynplaiSignError as exc:
        raise SignatureError(str(exc)) from exc

    whatsapp_instance = str(getattr(budget.workshop, "whatsapp_instance_name", "") or "").strip()

    try:
        result = get_signature_service().send_document(
            SignatureSendRequest(
                pdf_bytes=pdf_bytes,
                file_name=file_name,
                document_ref_id=f"budget-{budget.id}",
                title=title,
                message="Segue orcamento para assinatura.",
                signatory=signatory,
                observers=observers,
                fields=_build_signature_fields(budget),
                api_key=api_key,
                whatsapp_instance=whatsapp_instance,
            )
        )
    except SignatureServiceError as exc:
        raise SignatureError(str(exc)) from exc

    return result
