from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.urls import reverse

from apps.finance.models import NfseBatch, NfseItem, NfseRequest
from apps.finance.services.mappers import extract_items_from_batch, map_batch_payload, map_item_payload
from apps.finance.services.webmania_auth import WebmaniaAuthError, build_webmania_headers, redact_webmania_headers, sanitize_webmania_setting
from apps.finance.services.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


logger = logging.getLogger(__name__)


class NfseEmissionError(Exception):
    pass


def _is_debug_enabled() -> bool:
    return bool(getattr(settings, "NFSE_DEBUG_LOGS", True))


def _debug_print(message: str, payload: Any | None = None) -> None:
    if not _is_debug_enabled():
        return

    prefix = "[NFS-E DEBUG]"
    if payload is None:
        print(f"{prefix} {message}")
        return

    try:
        serialized = json.dumps(payload, ensure_ascii=False, default=str)
    except TypeError:
        serialized = str(payload)
    print(f"{prefix} {message}: {serialized}")


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return redact_webmania_headers(headers)


def build_webmania_webhook_token() -> str:
    explicit_token = sanitize_webmania_setting(getattr(settings, "WEBMANIA_WEBHOOK_TOKEN", ""))
    if explicit_token:
        return explicit_token

    signer = signing.Signer(salt="finance.webmania.webhook")
    return signer.sign("webmania")


def build_webmania_webhook_url(*, request=None) -> str:
    path = reverse("finance:webhook")
    token = build_webmania_webhook_token()
    path_with_query = f"{path}?{urlencode({'token': token})}"

    base_url = sanitize_webmania_setting(getattr(settings, "APP_BASE_URL", "")).rstrip("/")
    if base_url:
        return f"{base_url}{path_with_query}"

    if request is not None:
        return request.build_absolute_uri(path_with_query)

    return f"http://localhost:8000{path_with_query}"


def _build_headers(*, workshop) -> dict[str, str]:
    try:
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfseEmissionError(str(exc)) from exc


def _build_emit_url() -> str:
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_BASE_URL", "https://api.webmania.com.br/2/")).rstrip("/")
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

    if amount <= 0:
        raise NfseEmissionError("A OS selecionada não possui valor de serviços para emissão de NFS-e.")

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
    headers = _build_headers(workshop=nfse_request.workshop)

    _debug_print(
        "Iniciando emissao de NFS-e",
        {
            "nfse_request_id": nfse_request.pk,
            "workorder_id": nfse_request.workorder.pk,
        },
    )
    _debug_print("URL de emissao", emit_url)
    _debug_print("Headers de emissao", _redact_headers(headers))
    _debug_print("Payload de emissao", payload)

    try:
        response = requests.post(
            emit_url,
            json=payload,
            headers=headers,
            timeout=30,
        )
        _debug_print("Status HTTP da emissao", response.status_code)
        _debug_print("Body bruto da emissao", response.text)
        response.raise_for_status()
    except requests.RequestException as exc:
        error_message = build_webmania_request_exception_message(exc, default="Falha ao emitir NFS-e", scope="nfse")
        _debug_print("Falha HTTP na emissao", error_message)
        logger.exception("Erro ao emitir NFS-e", extra={"workorder_id": nfse_request.workorder.pk})
        raise NfseEmissionError(error_message) from exc

    try:
        data = response.json()
    except ValueError as exc:
        _debug_print("Resposta nao e JSON", response.text)
        raise NfseEmissionError("Resposta inválida da API de emissão de NFS-e.") from exc

    _debug_print("JSON parseado da emissao", data)

    if not isinstance(data, dict):
        raise NfseEmissionError("Resposta inválida da API de emissão de NFS-e.")

    error_message = extract_webmania_error_message(data.get("error"), scope="nfse")
    if error_message:
        _debug_print("Erro de negocio retornado pela API", error_message)
        raise NfseEmissionError(error_message)

    if not data.get("modelo") and not data.get("uuid"):
        message = extract_webmania_error_message(data.get("msg") or data.get("message"), scope="nfse")
        if not message:
            message = "Resposta da API sem modelo/uuid."
        _debug_print("Resposta sem dados esperados de emissao", data)
        raise NfseEmissionError(message)

    return data


def sync_emission_response(*, nfse_request: NfseRequest, response_payload: dict[str, Any]) -> None:
    _debug_print("Iniciando sincronizacao da resposta", response_payload)

    model = response_payload.get("modelo")
    if model not in {"lote_rps", "nfse"}:
        _debug_print("Modelo de resposta nao suportado para sincronizacao", model)
        return

    with transaction.atomic():
        if model == "lote_rps":
            mapped_batch = map_batch_payload(response_payload)
            batch_uuid = mapped_batch.pop("uuid", None)
            if not batch_uuid:
                _debug_print("Lote sem UUID, sincronizacao ignorada", response_payload)
                return

            batch, batch_created = NfseBatch.objects.update_or_create(
                workorder=nfse_request.workorder,
                uuid=batch_uuid,
                defaults={
                    "workshop": nfse_request.workshop,
                    "request": nfse_request,
                    "raw_payload": response_payload,
                    **mapped_batch,
                },
            )
            _debug_print(
                "Batch sincronizado",
                {
                    "uuid": str(batch.uuid),
                    "created": batch_created,
                    "status": batch.status,
                },
            )

            created_items = 0
            updated_items = 0

            for item_payload in extract_items_from_batch(response_payload):
                item_uuid = item_payload.pop("uuid", None)
                if not item_uuid:
                    continue

                _, item_created = NfseItem.objects.update_or_create(
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

                if item_created:
                    created_items += 1
                else:
                    updated_items += 1

            _debug_print(
                "Itens sincronizados a partir do lote",
                {
                    "created": created_items,
                    "updated": updated_items,
                },
            )

            return

        mapped_item = map_item_payload(response_payload)
        item_uuid = mapped_item.pop("uuid", None)
        if not item_uuid:
            _debug_print("NFS-e sem UUID, sincronizacao ignorada", response_payload)
            return

        item, item_created = NfseItem.objects.update_or_create(
            workorder=nfse_request.workorder,
            uuid=item_uuid,
            defaults={
                "workshop": nfse_request.workshop,
                "request": nfse_request,
                "raw_payload": response_payload,
                **mapped_item,
            },
        )
        _debug_print(
            "Item de NFS-e sincronizado",
            {
                "uuid": str(item.uuid),
                "created": item_created,
                "status": item.status,
            },
        )
