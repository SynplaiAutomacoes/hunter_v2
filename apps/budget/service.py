from dataclasses import dataclass
import re

from django.conf import settings
from django.core import signing
from django.urls import reverse

from apps.budget.documents.provider import render_budget_pdf_document
from apps.core.documents.services import (
    SignatureDeliveryServiceError,
    download_signed_document_content,
    get_signed_document_url,
    send_document_for_signature,
)


SIGNATURE_POSITION = {
    "x": 443.0,
    "y": 95.0,
    "width": 120.0,
    "height": 38.0,
}


def build_signature_payload(budget) -> dict:
    return {
        "budget_id": budget.id,
        "version": budget.signature_token_version,
    }


def build_signature_file_url(*, budget, request=None) -> str:
    payload = build_signature_payload(budget)
    token = signing.dumps(payload, salt="budget-signature-file")
    path = reverse("budget:signature_file", args=[token])

    if request is not None:
        return request.build_absolute_uri(path)

    base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/")
    if not base_url:
        base_url = "http://localhost:8000"

    return f"{base_url}{path}"


def build_signature_preview_url(*, budget, request=None) -> str:
    payload = build_signature_payload(budget)
    token = signing.dumps(payload, salt="budget-signature-file")
    path = reverse("budget:signature_preview", args=[token])

    if request is not None:
        return request.build_absolute_uri(path)

    base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/")
    if not base_url:
        base_url = "http://localhost:8000"

    return f"{base_url}{path}"


def build_supersign_webhook_url(*, request=None) -> str:
    path = reverse("budget:supersign_webhook")
    if request is not None:
        return request.build_absolute_uri(path)

    base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/")
    if not base_url:
        base_url = "http://localhost:8000"
    return f"{base_url}{path}"


class SuperSignError(Exception):
    pass


@dataclass
class SuperSignResult:
    envelope_id: str
    document_id: str
    raw_response: dict


def _normalize_phone_number(raw_phone: object) -> str:
    if raw_phone is None:
        return ""

    phone = str(raw_phone).strip()
    if not phone:
        return ""

    phone = re.sub(r"[^\d+]", "", phone)
    if not phone:
        return ""

    if phone.startswith("+"):
        return "+" + re.sub(r"\D", "", phone)

    digits = re.sub(r"\D", "", phone)
    if digits:
        return f"+{digits}"

    return ""


def list_supersign_webhooks() -> list[dict]:
    import requests

    base_url = settings.SUPERSIGN_BASE_URL.rstrip("/")
    try:
        response = requests.get(
            f"{base_url}/v2/webhooks/",
            headers={
                "x-account-id": settings.SUPERSIGN_ACCOUNT_ID,
                "Authorization": f"Bearer {settings.SUPERSIGN_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        raise SuperSignError(f"Erro ao listar webhooks: {exc}. Resposta: {response_text}") from exc

    data = response.json()
    return data if isinstance(data, list) else []


def create_supersign_webhook(*, url: str, events: list[str] | None = None, is_active: bool = True) -> dict:
    import requests

    base_url = settings.SUPERSIGN_BASE_URL.rstrip("/")
    payload = {
        "url": url,
        "events": events or ["ENVELOPE_COMPLETED"],
        "isActive": is_active,
    }

    try:
        response = requests.post(
            f"{base_url}/v2/webhooks/",
            json=payload,
            headers={
                "x-account-id": settings.SUPERSIGN_ACCOUNT_ID,
                "Authorization": f"Bearer {settings.SUPERSIGN_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        raise SuperSignError(f"Erro ao criar webhook: {exc}. Resposta: {response_text}") from exc

    data = response.json()
    return data if isinstance(data, dict) else {}


def ensure_supersign_webhook(*, webhook_url: str) -> dict:
    existing = list_supersign_webhooks()
    for webhook in existing:
        if webhook.get("url") == webhook_url and "ENVELOPE_COMPLETED" in (webhook.get("events") or []):
            return webhook

    return create_supersign_webhook(url=webhook_url, events=["ENVELOPE_COMPLETED"], is_active=True)


def get_supersign_signed_document_download_url(*, document_id: str) -> str:
    try:
        return get_signed_document_url(document_id=document_id)
    except SignatureDeliveryServiceError as exc:
        raise SuperSignError(str(exc)) from exc


def download_supersign_signed_pdf(*, document_id: str) -> bytes:
    try:
        return download_signed_document_content(document_id=document_id)
    except SignatureDeliveryServiceError as exc:
        raise SuperSignError(str(exc)) from exc


def _calculate_pdf_total_pages(budget) -> int:
    return 1


def _build_signature_fields(budget) -> list[dict]:
    document_ref_id = f"budget-{budget.id}"
    signatory_ref_id = f"customer-{budget.id}"

    return [
        {
            "type": "SIGNATURE",
            "documentId": document_ref_id,
            "signatoryId": signatory_ref_id,
            "pageNumber": 1,
            "position": SIGNATURE_POSITION,
            "properties": {},
        }
    ]


def _build_budget_pdf_bytes(*, budget, request=None) -> bytes:
    try:
        return render_budget_pdf_document(budget=budget, request=request).content
    except Exception as exc:
        raise SuperSignError(f"Erro ao gerar PDF para assinatura via Playwright: {exc}") from exc


def send_budget_for_signature(*, budget, request=None) -> SuperSignResult:
    customer_email = getattr(budget.customer, "email", "") if budget.customer else ""
    customer_phone = getattr(budget.customer, "phone", "") if budget.customer else ""
    normalized_phone = _normalize_phone_number(customer_phone)

    if not budget.customer:
        raise SuperSignError("Orçamento sem cliente vinculado para assinatura")

    if not customer_email:
        raise SuperSignError("Cliente sem email para assinatura")

    signatory = {
        "id": f"customer-{budget.id}",
        "name": budget.customer.name,
        "email": customer_email,
        "qualification": "Cliente",
        "signingOrder": 0,
        "authMethod": "EMAIL",
    }

    observers: list[dict] = []
    if normalized_phone:
        signatory["authMethod"] = "WHATSAPP"
        signatory["phoneNumber"] = normalized_phone
        observers.append(
            {
                "email": customer_email,
                "notifyOnSent": True,
                "notifyOnCompletion": True,
            }
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

    return SuperSignResult(
        envelope_id=result.envelope_id,
        document_id=result.document_id,
        raw_response=result.raw_response,
    )
