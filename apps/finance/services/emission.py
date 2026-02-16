from __future__ import annotations

import logging
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from django.urls import reverse

from apps.finance.models import NfseBatch, NfseItem, NfseRequest
from apps.finance.services.mappers import extract_items_from_batch, map_batch_payload, map_item_payload


logger = logging.getLogger(__name__)


class NfseEmissionError(Exception):
    pass


def build_webmania_webhook_url(*, request=None) -> str:
    path = reverse("finance:webhook")
    if request is not None:
        return request.build_absolute_uri(path)

    base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/")
    if not base_url:
        base_url = "http://localhost:8000"
    return f"{base_url}{path}"


def _build_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}

    api_key = getattr(settings, "WEBMANIA_API_KEY", "").strip()

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    return headers


def _build_emit_url() -> str:
    base_url = getattr(settings, "WEBMANIA_BASE_URL", "https://api.webmania.com.br/2/").rstrip("/")
    return f"{base_url}/nfse/emissao/"


def _build_taker_payload(nfse_request: NfseRequest) -> dict[str, str]:
    customer = nfse_request.workorder.budget.customer
    if not customer:
        raise NfseEmissionError("A OS selecionada não possui cliente vinculado.")

    document = re.sub(r"\D", "", customer.cpf_or_cnpj or "")
    if len(document) == 11:
        return {
            "cpf": customer.cpf_or_cnpj,
            "nome_completo": customer.name,
        }
    if len(document) == 14:
        return {
            "cnpj": customer.cpf_or_cnpj,
            "nome_completo": customer.name,
        }

    raise NfseEmissionError("Documento do cliente inválido para emissão da NFS-e.")


def _default_service_description(nfse_request: NfseRequest) -> str:
    if nfse_request.service_description.strip():
        return nfse_request.service_description.strip()

    budget = nfse_request.workorder.budget
    service_descriptions: list[str] = []

    for item in budget.items.select_related("service", "kit").all():
        if item.service or (item.is_local and item.service_selling_price.amount > 0):
            service_descriptions.append(f"{item.quantity}x {item.description}")
            continue

        if item.kit and item.get_kit_services_total().amount > 0:
            service_descriptions.append(f"{item.quantity}x {item.description} (Serviços do Kit)")

    if service_descriptions:
        return "; ".join(service_descriptions)

    return f"Prestação de serviço referente à OS #{nfse_request.workorder.pk}"


def _service_total_value(nfse_request: NfseRequest) -> str:
    amount = Decimal(nfse_request.workorder.budget.total_services_value.amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return str(amount)


def build_nfse_payload(*, nfse_request: NfseRequest, request=None) -> dict[str, Any]:
    ambiente = int(getattr(settings, "WEBMANIA_AMBIENT", "2"))
    notification_url = build_webmania_webhook_url(request=request)

    payload = {
        "ambiente": ambiente,
        "url_notificacao": notification_url,
        "rps": [
            {
                "servico": {
                    "valor_servicos": _service_total_value(nfse_request),
                    "discriminacao": _default_service_description(nfse_request),
                    "classe_imposto": nfse_request.tax_class,
                },
                "tomador": _build_taker_payload(nfse_request),
            }
        ],
    }
    return payload


def emit_nfse_request(*, nfse_request: NfseRequest, request=None) -> dict[str, Any]:
    payload = build_nfse_payload(nfse_request=nfse_request, request=request)
    emit_url = _build_emit_url()

    try:
        response = requests.post(
            emit_url,
            json=payload,
            headers=_build_headers(),
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        response_text = exc.response.text if exc.response is not None else ""
        logger.exception("Erro ao emitir NFS-e", extra={"workorder_id": nfse_request.workorder_id})
        raise NfseEmissionError(f"Falha ao emitir NFS-e: {response_text or str(exc)}") from exc

    data = response.json()
    if not isinstance(data, dict):
        raise NfseEmissionError("Resposta inválida da API de emissão de NFS-e.")

    return data


def sync_emission_response(*, nfse_request: NfseRequest, response_payload: dict[str, Any]) -> None:
    model = response_payload.get("modelo")
    if model not in {"lote_rps", "nfse"}:
        return

    with transaction.atomic():
        if model == "lote_rps":
            mapped_batch = map_batch_payload(response_payload)
            batch_uuid = mapped_batch.pop("uuid", None)
            if not batch_uuid:
                return

            batch, _ = NfseBatch.objects.update_or_create(
                workorder=nfse_request.workorder,
                uuid=batch_uuid,
                defaults={
                    "workshop": nfse_request.workshop,
                    "request": nfse_request,
                    "raw_payload": response_payload,
                    **mapped_batch,
                },
            )

            for item_payload in extract_items_from_batch(response_payload):
                item_uuid = item_payload.pop("uuid", None)
                if not item_uuid:
                    continue

                NfseItem.objects.update_or_create(
                    workorder=nfse_request.workorder,
                    uuid=item_uuid,
                    defaults={
                        "workshop": nfse_request.workshop,
                        "request": nfse_request,
                        "batch": batch,
                        "raw_payload": response_payload,
                        **item_payload,
                    },
                )

            return

        mapped_item = map_item_payload(response_payload)
        item_uuid = mapped_item.pop("uuid", None)
        if not item_uuid:
            return

        NfseItem.objects.update_or_create(
            workorder=nfse_request.workorder,
            uuid=item_uuid,
            defaults={
                "workshop": nfse_request.workshop,
                "request": nfse_request,
                "raw_payload": response_payload,
                **mapped_item,
            },
        )
