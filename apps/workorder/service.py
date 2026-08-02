from __future__ import annotations

from apps.core.domain.contracts.documents import SignatureRecipient
from apps.core.domain.contracts.signature import SignatureSendRequest, SignatureSendResult, SignatureServiceError
from apps.core.infrastructure.providers import get_signature_service
from apps.workorder.documents.provider import render_workorder_pdf_document
from apps.workshops.services.synplaisign import WorkshopSynplaiSignError, get_workshop_synplaisign_api_key


WORKORDER_SIGNATURE_TOKEN_SALT = "workorder-signature-file"
WORKORDER_SIGNATURE_DOCUMENT_ID_KEY = "workorder_id"
WORKORDER_SIGNATURE_FILE_ROUTE = "workorder:signature_file"
WORKORDER_SIGNATURE_PREVIEW_ROUTE = "workorder:signature_preview"


class WorkOrderSignatureError(Exception):
    pass


def build_signature_payload(workorder) -> dict:
    return get_signature_service().build_signature_payload(
        document_id_key=WORKORDER_SIGNATURE_DOCUMENT_ID_KEY,
        document_id=workorder.id,
        version=workorder.signature_token_version,
    )


def build_signature_file_url(*, workorder, request=None) -> str:
    return get_signature_service().build_signature_url(
        route_name=WORKORDER_SIGNATURE_FILE_ROUTE,
        token_salt=WORKORDER_SIGNATURE_TOKEN_SALT,
        document_id_key=WORKORDER_SIGNATURE_DOCUMENT_ID_KEY,
        document_id=workorder.id,
        version=workorder.signature_token_version,
        request=request,
    )


def build_signature_preview_url(*, workorder, request=None) -> str:
    return get_signature_service().build_signature_url(
        route_name=WORKORDER_SIGNATURE_PREVIEW_ROUTE,
        token_salt=WORKORDER_SIGNATURE_TOKEN_SALT,
        document_id_key=WORKORDER_SIGNATURE_DOCUMENT_ID_KEY,
        document_id=workorder.id,
        version=workorder.signature_token_version,
        request=request,
    )


def _build_signature_fields(workorder) -> list[dict]:
    return get_signature_service().build_signature_fields(
        document_ref_id=f"workorder-{workorder.id}",
        signatory_ref_id=f"customer-{workorder.id}",
        page_number=_calculate_pdf_total_pages(workorder),
    )


def _build_workorder_pdf_bytes(*, workorder) -> bytes:
    try:
        return render_workorder_pdf_document(workorder=workorder).content
    except Exception as exc:
        raise WorkOrderSignatureError(f"Erro ao gerar PDF da O.S. para assinatura via Playwright: {exc}") from exc


def _calculate_pdf_total_pages(workorder) -> int:
    return 1


def send_workorder_for_signature(*, workorder) -> SignatureSendResult:
    budget = workorder.budget
    customer = budget.customer
    customer_email = getattr(customer, "email", "") if customer else ""
    customer_phone = getattr(customer, "phone", "") if customer else ""

    if not budget.service_expected_completion_at:
        raise WorkOrderSignatureError("Não é possível enviar para assinatura antes de definir a data prevista de término do serviço.")

    if not customer:
        raise WorkOrderSignatureError("Ordem de serviço sem cliente vinculado para assinatura")

    if not customer_email:
        raise WorkOrderSignatureError("Cliente sem email para assinatura")

    signatory, observers = get_signature_service().build_signatory_and_observers(
        signatory_id=f"customer-{workorder.id}",
        recipient=SignatureRecipient(
            name=customer.name,
            email=customer_email,
            phone=customer_phone,
        ),
    )

    pdf_bytes = _build_workorder_pdf_bytes(workorder=workorder)
    file_name = f"ordem_servico-{workorder.get_id}.pdf"
    title = f"Ordem de servico #{workorder.get_id}"

    try:
        api_key = get_workshop_synplaisign_api_key(workorder.workshop)
    except WorkshopSynplaiSignError as exc:
        raise WorkOrderSignatureError(str(exc)) from exc

    try:
        result = get_signature_service().send_document(
            SignatureSendRequest(
                pdf_bytes=pdf_bytes,
                file_name=file_name,
                document_ref_id=f"workorder-{workorder.id}",
                title=title,
                message="Segue ordem de servico para assinatura.",
                signatory=signatory,
                observers=observers,
                fields=_build_signature_fields(workorder),
                api_key=api_key,
            )
        )
    except SignatureServiceError as exc:
        raise WorkOrderSignatureError(str(exc)) from exc

    return result
