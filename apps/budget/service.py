from dataclasses import dataclass

import requests
from django.core import signing
from django.conf import settings
from django.urls import reverse

from apps.core.pdf_playwright import render_pdf_from_url


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


class SuperSignError(Exception):
    pass


@dataclass
class SuperSignResult:
    envelope_id: str
    document_id: str
    raw_response: dict


def _build_budget_pdf_bytes(*, budget, request=None) -> bytes:
    preview_url = build_signature_preview_url(budget=budget, request=request)

    try:
        return render_pdf_from_url(preview_url)
    except Exception as exc:
        raise SuperSignError(f"Erro ao gerar PDF para assinatura via Playwright: {exc}") from exc


def send_budget_for_signature(*, budget, request=None) -> SuperSignResult:
    customer_email = getattr(budget.customer, "email", "") if budget.customer else ""
    if not budget.customer or not customer_email:
        raise SuperSignError("Cliente sem email para assinatura")

    pdf_bytes = _build_budget_pdf_bytes(budget=budget, request=request)
    file_name = f"orcamento-{budget.id}.pdf"

    create_payload = {
        "folderId": getattr(settings, "SUPERSIGN_FOLDER_ID", ""),
        "title": f"Orcamento #{budget.id}",
        "message": "Segue orcamento para assinatura.",
        "documents": [
            {
                "id": f"budget-{budget.id}",
                "fileName": file_name,
                "contentType": "application/pdf",
            }
        ],
        "signatories": [
            {
                "id": f"customer-{budget.id}",
                "name": budget.customer.name,
                "email": customer_email,
                "qualification": "Cliente",
                "signingOrder": 0,
                "authMethod": "EMAIL",
            }
        ],
        "observers": [],
        "fields": [],
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
