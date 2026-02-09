import os
from dataclasses import dataclass
from io import BytesIO

import requests
from django.core import signing
from django.urls import reverse
from django.conf import settings

from apps.core.utils import render_to_pdf


def build_signature_payload(budget) -> dict:
    return {
        "budget_id": budget.id,
        "version": budget.signature_token_version,
    }

def build_signature_file_url(*, budget, request=None) -> str:
    payload = build_signature_payload(budget)
    token = signing.dumps(payload, salt="budget-signature-file")
    path = reverse("budget:signature-file", args=[token])

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

def _build_budget_pdf_bytes(budget) -> bytes:
    itens_all = budget.items.all()
    produtos = itens_all.filter(product__isnull=False)
    servicos = itens_all.filter(service__isnull=False)

    context = {
        "budget": budget,
        "produtos": produtos,
        "servicos": servicos,
        "total_produtos": budget.total_products_value,
        "total_servicos": budget.total_services_value,
        "desconto": budget.discount_value,
        "total_geral": budget.total_budget_value,
        "observacao": budget.workshop.pdf_observation
    }

    pdf_buffer: BytesIO | None = render_to_pdf("budget/partials/pdf/visualizarPDF.html", context)
    if not pdf_buffer:
        raise SuperSignError("Erro ao gerar PDF para assinatura")

    return pdf_buffer.getvalue()


def send_budget_for_signature(*, budget) -> SuperSignResult:
    if not budget.customer or not budget.customer.email:
        raise SuperSignError("Cliente sem email para assinatura")

    pdf_bytes = _build_budget_pdf_bytes(budget)
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
                "email": budget.customer.email,
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
        raise SuperSignError(f"Erro ao criar envelope: {exc}") from exc

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

    # 2) upload do PDF para a URL assinada retornada
    try:
        upload_resp = requests.put(
            upload_url,
            data=pdf_bytes,
            headers={"Content-Type": "application/pdf"},
            timeout=30,
        )
        upload_resp.raise_for_status()
    except requests.RequestException as exc:
        raise SuperSignError(f"Erro ao enviar arquivo para uploadUrl: {exc}") from exc

    # 3) opcional: enviar/finalizar envelope (ver endpoint exato na sua conta)
    # requests.post(f"{base_url}/v2/envelopes/{envelope_id}/send", headers=headers, timeout=20)

    return SuperSignResult(
        envelope_id=str(envelope_id),
        document_id=str(document_id),
        raw_response=create_data,
    )