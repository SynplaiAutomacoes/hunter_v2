from dataclasses import dataclass
import re

import requests
from django.core import signing
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse

from apps.budget.pdf_context import build_budget_pdf_context
from apps.core.pdf_playwright import render_pdf_from_html


PRODUCTS_PER_PAGE = 4
SERVICES_PER_PAGE = 2
SIGNATURE_POSITION = {
    "x": 170.14,
    "y": 689.69,
    "width": 254.25,
    "height": 30.4,
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


def _supersign_headers() -> dict[str, str]:
    return {
        "x-account-id": settings.SUPERSIGN_ACCOUNT_ID,
        "Authorization": f"Bearer {settings.SUPERSIGN_API_KEY}",
        "Content-Type": "application/json",
    }


def list_supersign_webhooks() -> list[dict]:
    base_url = settings.SUPERSIGN_BASE_URL.rstrip("/")
    try:
        response = requests.get(f"{base_url}/v2/webhooks/", headers=_supersign_headers(), timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        raise SuperSignError(f"Erro ao listar webhooks: {exc}. Resposta: {response_text}") from exc

    data = response.json()
    return data if isinstance(data, list) else []


def create_supersign_webhook(*, url: str, events: list[str] | None = None, is_active: bool = True) -> dict:
    base_url = settings.SUPERSIGN_BASE_URL.rstrip("/")
    payload = {
        "url": url,
        "events": events or ["ENVELOPE_COMPLETED"],
        "isActive": is_active,
    }

    try:
        response = requests.post(f"{base_url}/v2/webhooks/", json=payload, headers=_supersign_headers(), timeout=20)
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
    base_url = settings.SUPERSIGN_BASE_URL.rstrip("/")
    try:
        response = requests.get(
            f"{base_url}/v2/documents/{document_id}/download",
            headers=_supersign_headers(),
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        raise SuperSignError(f"Erro ao buscar downloadUrl do documento assinado: {exc}. Resposta: {response_text}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise SuperSignError("Resposta invalida ao buscar downloadUrl do documento assinado") from exc

    download_url = data.get("downloadUrl") if isinstance(data, dict) else None
    if not isinstance(download_url, str) or not download_url.strip():
        raise SuperSignError("Resposta sem downloadUrl para documento assinado")

    return download_url.strip()


def download_supersign_signed_pdf(*, document_id: str) -> bytes:
    download_url = get_supersign_signed_document_download_url(document_id=document_id)

    try:
        response = requests.get(download_url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        raise SuperSignError(f"Erro ao baixar PDF assinado: {exc}. Resposta: {response_text}") from exc

    content_type = (response.headers.get("Content-Type") or "").lower()
    pdf_signature = b"%PDF"
    if "application/pdf" not in content_type and not response.content.startswith(pdf_signature):
        raise SuperSignError("Arquivo retornado nao possui formato PDF")

    return response.content


def _calculate_pdf_total_pages(budget) -> int:
    products_count = budget.items.filter(product__isnull=False).count()
    services_count = budget.items.filter(service__isnull=False).count()

    products_pages = (products_count + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE
    services_pages = (services_count + SERVICES_PER_PAGE - 1) // SERVICES_PER_PAGE

    return max(products_pages, services_pages, 1)


def _build_signature_fields(budget) -> list[dict]:
    total_pages = _calculate_pdf_total_pages(budget)
    document_ref_id = f"budget-{budget.id}"
    signatory_ref_id = f"customer-{budget.id}"

    return [
        {
            "type": "SIGNATURE",
            "documentId": document_ref_id,
            "signatoryId": signatory_ref_id,
            "pageNumber": page_number,
            "position": SIGNATURE_POSITION,
            "properties": {},
        }
        for page_number in range(1, total_pages + 1)
    ]


def _build_budget_pdf_bytes(*, budget, request=None) -> bytes:
    context = build_budget_pdf_context(budget=budget, observacao=budget.workshop.pdf_observation)
    html = render_to_string("budget/partials/pdf/visualizarPDF.html", context)

    try:
        return render_pdf_from_html(html)
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

    document_ref_id = f"budget-{budget.id}"
    create_payload = {
        "folderId": getattr(settings, "SUPERSIGN_FOLDER_ID", ""),
        "title": f"Orcamento #{budget.id}",
        "message": "Segue orcamento para assinatura.",
        "documents": [
            {
                "id": document_ref_id,
                "fileName": file_name,
                "contentType": "application/pdf",
            }
        ],
        "signatories": [signatory],
        "observers": observers,
        "fields": _build_signature_fields(budget),
    }

    headers = {
        "x-account-id": settings.SUPERSIGN_ACCOUNT_ID,
        "Authorization": f"Bearer {settings.SUPERSIGN_API_KEY}",
        "Content-Type": "application/json",
    }

    base_url = settings.SUPERSIGN_BASE_URL.rstrip("/")

    # 1) cria envelope
    try:
        create_resp = requests.post(
            f"{base_url}/v2/envelopes/",
            json=create_payload,
            headers=headers,
            timeout=20,
        )
        create_resp.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        raise SuperSignError(f"Erro ao criar envelope: {exc}. Resposta: {response_text}") from exc

    create_data = create_resp.json()
    envelope_id = create_data.get("envelopeId")
    upload_details = create_data.get("uploadDetails") or []
    if not envelope_id or not upload_details:
        raise SuperSignError("Resposta sem envelopeId/uploadDetails")

    first_upload = upload_details[0]
    document_id = first_upload.get("documentId")
    upload_url = first_upload.get("uploadUrl")
    if not document_id or not upload_url:
        raise SuperSignError("uploadDetails incompleto")

    upload_headers = {"Content-Type": "application/pdf", "x-goog-meta-documentid": str(document_id)}

    # 2) upload do PDF para a URL assinada retornada
    try:
        upload_resp = requests.put(
            upload_url,
            data=pdf_bytes,
            headers=upload_headers,
            timeout=30,
        )
        upload_resp.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        raise SuperSignError(f"Erro ao enviar arquivo para uploadUrl: {exc}. Resposta: {response_text}") from exc

    return SuperSignResult(
        envelope_id=str(envelope_id),
        document_id=str(document_id),
        raw_response=create_data,
    )
