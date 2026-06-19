from __future__ import annotations

from copy import deepcopy
import json
import logging
import re
import time
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import urlencode, urlparse

import requests
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.http import HttpRequest
from django.urls import reverse

from apps.finance.models.finance import NfseBatch, NfseItem, NfseRequest
from apps.finance.services.numbering import EmissionNumberReservationError, reserve_nfse_request_rps_number
from apps.finance.services.mappers import extract_items_from_batch, map_batch_payload, map_item_payload
from apps.finance.services.pricing import build_nfse_service_preview_rows, build_slider_allocation_for_workorder
from apps.workorder.models import WorkOrder, WorkOrderDiscountType
from apps.core.infrastructure.services.webmania.webmania_auth import (
    WebmaniaAuthError,
    build_webmania_headers,
    redact_webmania_headers,
    sanitize_webmania_setting,
    should_use_global_webmania_auth,
)
from apps.core.infrastructure.services.webmania.webmania_documents import DownloadedWebmaniaDocument
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message


logger = logging.getLogger(__name__)


class NfseEmissionError(Exception):
    pass


def build_default_service_description_for_workorder(*, workorder: Any) -> str:
    service_descriptions = [f"{row['quantity']}x {row['description']}" for row in build_nfse_service_preview_rows(workorder=workorder)]

    if service_descriptions:
        return "; ".join(service_descriptions)

    return f"Prestacao de servico referente a OS #{getattr(workorder, 'pk', '-')}"


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
    if base_url and _is_public_base_url(base_url):
        return f"{base_url}{path_with_query}"

    if request is not None:
        return request.build_absolute_uri(path_with_query)

    if base_url:
        return f"{base_url}{path_with_query}"

    return f"http://localhost:8000{path_with_query}"


def _is_public_base_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    hostname = str(parsed.hostname or "").strip().lower()
    if not hostname:
        return False
    if hostname in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return False
    return True


def _build_headers(*, workshop=None) -> dict[str, str]:
    try:
        if should_use_global_webmania_auth():
            return build_webmania_headers()
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise NfseEmissionError(str(exc)) from exc


def _build_emit_url() -> str:
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_BASE_URL", "https://api.webmania.com.br/2/")).rstrip("/")
    return f"{base_url}/nfse/emissao/"


def _build_cancel_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_NFSE_CANCEL_ENDPOINT", ""))
    if custom_endpoint:
        return f"{custom_endpoint.rstrip('/')}/"

    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_BASE_URL", "https://api.webmania.com.br/2/")).rstrip("/")
    return f"{base_url}/nfse/cancelar/"


def _build_tax_class_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_ENDPOINT", ""))
    if custom_endpoint:
        endpoint = custom_endpoint.rstrip("/")
        return f"{endpoint}/"

    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/classe-imposto/"


def _has_payload_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


def _is_tax_class_not_found_error(message: str) -> bool:
    normalized_message = (message or "").strip().lower()
    if "classe de imposto" not in normalized_message:
        return False
    return "nao encontrada" in normalized_message or "não encontrada" in normalized_message


def _is_nfse_tax_class(payload: dict[str, Any]) -> bool:
    tax_type = str(payload.get("tipo") or payload.get("type") or "").strip().lower()
    if tax_type in {"nfse", "nfs-e", "nsfe"}:
        return True

    return bool(str(payload.get("tipo_emissao") or "").strip()) and bool(str(payload.get("codigo_servico") or "").strip())


def _validate_tax_class_for_emission(*, nfse_request: NfseRequest, headers: dict[str, str]) -> dict[str, Any]:
    reference = str(nfse_request.tax_class or "").strip()
    if not reference:
        raise NfseEmissionError("Selecione uma classe de imposto para emitir a Nota Fiscal de Serviço.")

    endpoint = _build_tax_class_url()
    _debug_print("Validando classe de imposto para emissao", {"reference": reference, "endpoint": endpoint})

    try:
        response = requests.get(endpoint, headers=headers, timeout=30)
        _debug_print("Status HTTP da validacao de classe", response.status_code)
        _debug_print("Body bruto da validacao de classe", response.text)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao validar classe de imposto para emissão", scope="tax_class")
        _debug_print("Falha HTTP na validacao de classe", message)
        raise NfseEmissionError(message) from exc

    try:
        data = response.json()
    except ValueError as exc:
        _debug_print("Resposta da validacao de classe nao e JSON", response.text)
        raise NfseEmissionError("Resposta inválida da API ao validar classe de imposto.") from exc

    _debug_print("JSON parseado da validacao de classe", data)
    if not isinstance(data, list):
        if isinstance(data, dict):
            error_message = extract_webmania_error_message(data.get("error") or data.get("message") or data.get("msg"), scope="tax_class")
            if error_message:
                raise NfseEmissionError(error_message)
        raise NfseEmissionError("Resposta inválida da API ao validar classe de imposto.")

    matched_tax_class: dict[str, Any] | None = None
    for item in data:
        if not isinstance(item, dict):
            continue
        candidate_reference = str(item.get("referencia") or "").strip()
        if candidate_reference == reference:
            matched_tax_class = item
            break

    if not matched_tax_class:
        raise NfseEmissionError("A classe de imposto selecionada não está disponível para estas credenciais da Webmania. Atualize as classes e selecione uma referência válida.")

    if not _is_nfse_tax_class(matched_tax_class):
        raise NfseEmissionError("A classe de imposto selecionada não é do tipo Nota Fiscal de Serviço.")

    _debug_print(
        "Classe de imposto validada para emissao",
        {
            "reference": reference,
            "tipo": matched_tax_class.get("tipo") or matched_tax_class.get("type"),
            "status": matched_tax_class.get("status"),
        },
    )
    return matched_tax_class


def _build_fallback_payload_with_explicit_tax_data(*, payload: dict[str, Any], tax_class_payload: dict[str, Any]) -> dict[str, Any]:
    fallback_payload = deepcopy(payload)

    rps = fallback_payload.get("rps")
    if not isinstance(rps, list) or not rps:
        return fallback_payload
    first_rps = rps[0]
    if not isinstance(first_rps, dict):
        return fallback_payload

    service_payload = first_rps.get("servico")
    if not isinstance(service_payload, dict):
        service_payload = {}
        first_rps["servico"] = service_payload

    service_payload.pop("classe_imposto", None)

    service_fields = (
        "codigo_servico",
        "natureza_operacao",
        "iss_retido",
        "exigibilidade_iss",
        "tributacao_iss",
        "tipo_emissao",
        "codigo_tributacao_municipio",
        "tipo_imunidade",
        "responsavel_retencao",
        "codigo_cnae",
        "finalidade",
        "consumidor_final",
        "cod_indicador_operacao",
        "codigo_nbs",
        "cidade_local_prestacao",
        "uf_local_prestacao",
        "numero_processo",
        "deducoes",
        "desconto_incondicionado",
        "desconto_condicionado",
        "outras_retencoes",
    )
    for field_name in service_fields:
        if _has_payload_value(service_payload.get(field_name)):
            continue
        value = tax_class_payload.get(field_name)
        if _has_payload_value(value):
            service_payload[field_name] = value

    if not _has_payload_value(service_payload.get("iss_retido")):
        fallback_retencao_iss = tax_class_payload.get("retencao_iss")
        if _has_payload_value(fallback_retencao_iss):
            service_payload["iss_retido"] = fallback_retencao_iss

    impostos_payload_raw = service_payload.get("impostos")
    impostos_payload = dict(impostos_payload_raw) if isinstance(impostos_payload_raw, dict) else {}

    class_impostos_raw = tax_class_payload.get("impostos")
    class_impostos_payload = dict(class_impostos_raw) if isinstance(class_impostos_raw, dict) else {}
    for field_name, value in class_impostos_payload.items():
        if _has_payload_value(impostos_payload.get(field_name)):
            continue
        if _has_payload_value(value):
            impostos_payload[field_name] = value

    tax_fields = (
        "iss",
        "iss_simples_nacional",
        "reducao",
        "cst_pis_cofins",
        "pis",
        "cofins",
        "inss",
        "ir",
        "csll",
        "cp",
        "ibs_cbs",
    )
    for field_name in tax_fields:
        if _has_payload_value(impostos_payload.get(field_name)):
            continue
        value = tax_class_payload.get(field_name)
        if _has_payload_value(value):
            impostos_payload[field_name] = value

    if impostos_payload:
        service_payload["impostos"] = impostos_payload

    return fallback_payload


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
        razao_social = (customer.name or "").strip()
        if not razao_social:
            raise NfseEmissionError("Razão social do cliente é obrigatória para emissão da Nota Fiscal de Serviço com CNPJ.")

        return {
            "cnpj": customer.cpf_or_cnpj,
            "razao_social": razao_social,
        }

    raise NfseEmissionError("Documento do cliente inválido para emissão da Nota Fiscal de Serviço.")


def _default_service_description(nfse_request: NfseRequest) -> str:
    if nfse_request.service_description.strip():
        return nfse_request.service_description.strip()

    return build_default_service_description_for_workorder(workorder=nfse_request.workorder)


def _additional_information(nfse_request: NfseRequest) -> str:
    return str(getattr(nfse_request, "additional_information", "") or "").strip()


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _compute_service_discount_for_nfse(
    *,
    workorder: WorkOrder,
) -> Decimal:
    """
    Calcula o valor de desconto a ser aplicado nos servicos da NFS-e,
    levando em consideracao o discount_type da WorkOrder:

    - SERVICES: todo o desconto da WorkOrder vai para os servicos.
    - PRODUCTS: o desconto e inteiramente para produtos; apenas o excesso
      (quando total_discount > raw_products_total) vai para os servicos.
    - BOTH: o desconto e distribuido proporcionalmente entre produtos e
      servicos usando os valores brutos reais do pedido (independente do
      slider de alocacao da NFS-e).
    """
    total_discount = _quantize_money(Decimal(str(workorder.resolved_discount_value.amount)))
    if total_discount <= Decimal("0.00"):
        return Decimal("0.00")

    discount_type = workorder.discount_type

    if discount_type == WorkOrderDiscountType.SERVICES:
        return total_discount

    # Para PRODUCTS e BOTH, usa os valores brutos reais (pre-slider) do pedido.
    # O slider altera apenas a alocacao de receita para NF-e/NFS-e, mas nao
    # deve afetar a proporcao do desconto entre produtos e servicos.
    snapshot = workorder.pricing_snapshot
    raw_products = _quantize_money(Decimal(str(snapshot.total_products_value.amount)))
    raw_services = _quantize_money(Decimal(str(snapshot.total_services_value.amount)))

    if discount_type == WorkOrderDiscountType.PRODUCTS:
        # Desconto apenas para produtos; se superar o total de produtos, o excesso vai para servicos
        excess = _quantize_money(max(Decimal("0.00"), total_discount - raw_products))
        return excess

    # BOTH: distribuicao proporcional entre produtos e servicos pelos valores brutos
    raw_total = _quantize_money(raw_products + raw_services)
    if raw_total <= Decimal("0.00"):
        return Decimal("0.00")
    return _quantize_money(total_discount * raw_services / raw_total)


def _service_total_value(nfse_request: NfseRequest, *, slider_override: int | None = None) -> str:
    allocation = build_slider_allocation_for_workorder(
        workorder=nfse_request.workorder,
        persisted_slider=getattr(nfse_request, "pricing_slider", None),
        slider_override=slider_override,
    )
    gross_amount = allocation.services_target.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if gross_amount <= 0:
        raise NfseEmissionError("A OS selecionada nao possui saldo de servicos para emissao de Nota Fiscal de Serviço com a configuracao atual do slider.")

    service_discount = _compute_service_discount_for_nfse(workorder=nfse_request.workorder)
    net_amount = _quantize_money(gross_amount - service_discount)

    if net_amount <= 0:
        raise NfseEmissionError("O valor total do desconto aplicado e maior ou igual ao valor dos servicos para esta Nota Fiscal de Serviço.")

    return str(net_amount)


def build_nfse_payload(*, nfse_request: NfseRequest, request: HttpRequest | None = None, slider_override: int | None = None) -> dict[str, Any]:
    ambiente = int(getattr(settings, "WEBMANIA_AMBIENT", "2"))
    notification_url = build_webmania_webhook_url(request=request)

    first_rps: dict[str, Any] = {
        "servico": {
            "valor_servicos": _service_total_value(nfse_request, slider_override=slider_override),
            "discriminacao": _default_service_description(nfse_request),
            "classe_imposto": nfse_request.tax_class,
        },
        "tomador": _build_taker_payload(nfse_request),
    }
    additional_information = _additional_information(nfse_request)
    if additional_information:
        first_rps["servico"]["informacoes_complementares"] = additional_information
    if nfse_request.reserved_rps_number is not None:
        first_rps["numero"] = int(nfse_request.reserved_rps_number)
    if str(nfse_request.reserved_rps_series or "").strip():
        first_rps["serie"] = str(nfse_request.reserved_rps_series)

    payload = {
        "ID": str(nfse_request.pk),
        "ambiente": ambiente,
        "url_notificacao": notification_url,
        "rps": [first_rps],
    }

    first_rps = payload["rps"][0]
    taker_payload = first_rps.get("tomador") if isinstance(first_rps, dict) else {}
    taker_type = "pj" if isinstance(taker_payload, dict) and taker_payload.get("cnpj") else "pf"

    _debug_print(
        "Payload de emissao montado",
        {
            "nfse_request_id": nfse_request.pk,
            "workorder_id": nfse_request.workorder.pk,
            "ambiente": ambiente,
            "tax_class": nfse_request.tax_class,
            "taker_type": taker_type,
            "notification_url": notification_url,
        },
    )

    logger.info("nfse_payload_built", extra={"nfse_request_id": nfse_request.pk, "workshop_id": nfse_request.workshop.pk, "workorder_id": nfse_request.workorder.pk, "tax_class": str(nfse_request.tax_class or ""), "taker_type": taker_type})

    return payload


def _extract_nfse_preview_url(data: dict[str, Any]) -> str:
    for key in ("pdf_nfse", "danfe", "pdf", "url", "pdf_rps"):
        value = str(data.get(key) or "").strip()
        if value:
            return value
    return ""


def _is_json_content_type(content_type: str) -> bool:
    normalized_content_type = content_type.lower()
    return "application/json" in normalized_content_type or "text/json" in normalized_content_type


def _normalize_preview_message(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _is_preview_pending_message(message: str) -> bool:
    normalized_message = _normalize_preview_message(message)
    return "aguardando pdf" in normalized_message and "municipio" in normalized_message


def _extract_preview_pending_message_from_response(response: requests.Response) -> str:
    content_type = str(response.headers.get("Content-Type") or "").lower()

    if _is_json_content_type(content_type):
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            message = str(payload.get("msg") or payload.get("message") or payload.get("error") or "").strip()
            if message and _is_preview_pending_message(message):
                return message
        return ""

    body_text = response.text.strip()
    if body_text and _is_preview_pending_message(body_text):
        return body_text

    return ""


NFSE_PREVIEW_RETRY_DELAY_SECONDS = 10
NFSE_PREVIEW_MAX_ATTEMPTS = 5


def preview_nfse_request(*, nfse_request: NfseRequest, request: HttpRequest | None = None, slider_override: int | None = None) -> dict[str, Any]:
    emit_url = _build_emit_url()
    headers = _build_headers(workshop=nfse_request.workshop)

    tax_class_payload = _validate_tax_class_for_emission(nfse_request=nfse_request, headers=headers)
    payload = build_nfse_payload(nfse_request=nfse_request, request=request, slider_override=slider_override)
    payload["previa_danfe"] = True

    def _post_preview(current_payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.post(
                emit_url,
                json=current_payload,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            error_message = build_webmania_request_exception_message(exc, default="Falha ao gerar previa da Nota Fiscal de Serviço", scope="nfse")
            raise NfseEmissionError(error_message) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise NfseEmissionError("Resposta invalida da API de previa da Nota Fiscal de Serviço.") from exc

        if not isinstance(data, dict):
            raise NfseEmissionError("Resposta invalida da API de previa da Nota Fiscal de Serviço.")

        return data

    data = _post_preview(payload)
    error_message = extract_webmania_error_message(data.get("error") or data.get("msg") or data.get("message"), scope="nfse")
    if error_message and _is_tax_class_not_found_error(error_message):
        fallback_payload = _build_fallback_payload_with_explicit_tax_data(payload=payload, tax_class_payload=tax_class_payload)
        data = _post_preview(fallback_payload)
        error_message = extract_webmania_error_message(data.get("error") or data.get("msg") or data.get("message"), scope="nfse")

    if error_message:
        raise NfseEmissionError(error_message)

    preview_url = _extract_nfse_preview_url(data)
    if not preview_url:
        raise NfseEmissionError("A API da Webmania nao retornou a URL da previa da Nota Fiscal de Serviço.")

    return {**data, "preview_url": preview_url}


def download_nfse_preview_document(*, nfse_request: NfseRequest, request: HttpRequest | None = None, slider_override: int | None = None) -> DownloadedWebmaniaDocument:
    emit_url = _build_emit_url()
    headers = _build_headers(workshop=nfse_request.workshop)

    tax_class_payload = _validate_tax_class_for_emission(nfse_request=nfse_request, headers=headers)
    payload = build_nfse_payload(nfse_request=nfse_request, request=request, slider_override=slider_override)
    payload["previa_danfe"] = True

    def _post_preview(current_payload: dict[str, Any]) -> requests.Response:
        try:
            response = requests.post(
                emit_url,
                json=current_payload,
                headers=headers,
                timeout=60,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            error_message = build_webmania_request_exception_message(exc, default="Falha ao gerar previa da Nota Fiscal de Serviço", scope="nfse")
            raise NfseEmissionError(error_message) from exc
        return response

    def _parse_json(current_response: requests.Response) -> dict[str, Any]:
        try:
            data = current_response.json()
        except ValueError as exc:
            raise NfseEmissionError("Resposta invalida da API de previa da Nota Fiscal de Serviço.") from exc

        if not isinstance(data, dict):
            raise NfseEmissionError("Resposta invalida da API de previa da Nota Fiscal de Serviço.")
        return data

    def _response_to_document(current_response: requests.Response, *, current_payload: dict[str, Any]) -> DownloadedWebmaniaDocument | None:
        content_type = str(current_response.headers.get("Content-Type") or "application/pdf")
        if not _is_json_content_type(content_type):
            pending_message = _extract_preview_pending_message_from_response(current_response)
            if pending_message:
                return None

        data = _parse_json(current_response)
        raw_message = str(data.get("msg") or data.get("message") or "").strip()
        if raw_message and _is_preview_pending_message(raw_message):
            return None

        error_message = extract_webmania_error_message(data.get("error") or data.get("msg") or data.get("message"), scope="nfse")
        if error_message and _is_tax_class_not_found_error(error_message):
            fallback_payload = _build_fallback_payload_with_explicit_tax_data(payload=current_payload, tax_class_payload=tax_class_payload)
            fallback_response = _post_preview(fallback_payload)
            return _response_to_document(fallback_response, current_payload=fallback_payload)

        if error_message:
            raise NfseEmissionError(error_message)

        preview_url = _extract_nfse_preview_url(data)
        if not preview_url:
            raise NfseEmissionError("A API da Webmania nao retornou o PDF da previa da Nota Fiscal de Serviço.")

        for download_attempt in range(1, NFSE_PREVIEW_MAX_ATTEMPTS + 1):
            try:
                download_response = requests.get(preview_url, headers=headers, timeout=60)
                download_response.raise_for_status()
            except requests.RequestException as exc:
                error_message = build_webmania_request_exception_message(exc, default="Falha ao baixar previa da Nota Fiscal de Serviço", scope="nfse")
                raise NfseEmissionError(error_message) from exc

            pending_message = _extract_preview_pending_message_from_response(download_response)
            if pending_message:
                if download_attempt < NFSE_PREVIEW_MAX_ATTEMPTS:
                    time.sleep(NFSE_PREVIEW_RETRY_DELAY_SECONDS)
                    continue
                raise NfseEmissionError("O PDF da previa da Nota Fiscal de Serviço ainda esta sendo gerado pelo municipio. Tente novamente em alguns segundos.")

            download_content_type = str(download_response.headers.get("Content-Type") or "application/octet-stream")
            if "application/pdf" not in download_content_type.lower() and not download_response.content.startswith(b"%PDF"):
                raise NfseEmissionError("A previa da Nota Fiscal de Serviço ainda nao retornou um PDF valido. Tente novamente em alguns segundos.")

            return DownloadedWebmaniaDocument(
                content=download_response.content,
                content_type=download_content_type,
                content_disposition=str(download_response.headers.get("Content-Disposition") or ""),
            )

        raise NfseEmissionError("O PDF da previa da Nota Fiscal de Serviço ainda esta sendo gerado pelo municipio. Tente novamente em alguns segundos.")

    for attempt in range(1, NFSE_PREVIEW_MAX_ATTEMPTS + 1):
        response = _post_preview(payload)
        document = _response_to_document(response, current_payload=payload)
        if document is not None:
            return document

        if attempt < NFSE_PREVIEW_MAX_ATTEMPTS:
            time.sleep(NFSE_PREVIEW_RETRY_DELAY_SECONDS)

    raise NfseEmissionError("O PDF da previa da Nota Fiscal de Serviço ainda esta sendo gerado pelo municipio. Tente novamente em alguns segundos.")


def emit_nfse_request(*, nfse_request: NfseRequest, request: HttpRequest | None = None, slider_override: int | None = None) -> dict[str, Any]:
    emit_url = _build_emit_url()
    headers = _build_headers(workshop=nfse_request.workshop)

    tax_class_payload = _validate_tax_class_for_emission(nfse_request=nfse_request, headers=headers)

    if isinstance(nfse_request, NfseRequest):
        try:
            reserve_nfse_request_rps_number(nfse_request=nfse_request)
        except EmissionNumberReservationError as exc:
            raise NfseEmissionError(str(exc)) from exc

    payload = build_nfse_payload(nfse_request=nfse_request, request=request, slider_override=slider_override)

    _debug_print(
        "Iniciando emissao de Nota Fiscal de Serviço",
        {
            "nfse_request_id": nfse_request.pk,
            "workorder_id": nfse_request.workorder.pk,
        },
    )
    logger.info("nfse_emission_started", extra={"nfse_request_id": nfse_request.pk, "workshop_id": nfse_request.workshop.pk, "workorder_id": nfse_request.workorder.pk})
    _debug_print("URL de emissao", emit_url)
    _debug_print("Headers de emissao", _redact_headers(headers))
    _debug_print("Payload de emissao", payload)

    started_at = time.monotonic()
    try:
        response = requests.post(
            emit_url,
            json=payload,
            headers=headers,
            timeout=30,
        )
        elapsed_ms = round((time.monotonic() - started_at) * 1000, 2)
        _debug_print("Status HTTP da emissao", response.status_code)
        _debug_print("Body bruto da emissao", response.text)
        response.raise_for_status()
    except requests.RequestException as exc:
        elapsed_ms = round((time.monotonic() - started_at) * 1000, 2)
        error_message = build_webmania_request_exception_message(exc, default="Falha ao emitir Nota Fiscal de Serviço", scope="nfse")
        _debug_print("Falha HTTP na emissao", error_message)
        logger.exception("nfse_emission_failed", extra={"workorder_id": nfse_request.workorder.pk, "duration_ms": elapsed_ms})
        logger.warning("nfse_emission_http_error", extra={"nfse_request_id": nfse_request.pk, "workshop_id": nfse_request.workshop.pk, "error": error_message, "duration_ms": elapsed_ms})
        raise NfseEmissionError(error_message) from exc

    try:
        data = response.json()
    except ValueError as exc:
        _debug_print("Resposta nao e JSON", response.text)
        raise NfseEmissionError("Resposta inválida da API de emissão de Nota Fiscal de Serviço.") from exc

    _debug_print("JSON parseado da emissao", data)

    if not isinstance(data, dict):
        raise NfseEmissionError("Resposta inválida da API de emissão de Nota Fiscal de Serviço.")

    error_message = extract_webmania_error_message(data.get("error") or data.get("msg") or data.get("message"), scope="nfse")
    if error_message:
        _debug_print("Erro de negocio retornado pela API", error_message)
        logger.warning(
            "nfse_emission_business_error nfse_request_id=%s workshop_id=%s error=%s",
            getattr(nfse_request, "pk", None),
            getattr(nfse_request.workshop, "pk", None),
            error_message,
        )

        if _is_tax_class_not_found_error(error_message):
            fallback_payload = _build_fallback_payload_with_explicit_tax_data(payload=payload, tax_class_payload=tax_class_payload)
            _debug_print("Tentando emissao com impostos explicitos", fallback_payload)
            logger.info("nfse_emission_retry_with_explicit_tax_data", extra={"nfse_request_id": nfse_request.pk, "workshop_id": nfse_request.workshop.pk})

            retry_started_at = time.monotonic()
            try:
                fallback_response = requests.post(
                    emit_url,
                    json=fallback_payload,
                    headers=headers,
                    timeout=30,
                )
                retry_elapsed_ms = round((time.monotonic() - retry_started_at) * 1000, 2)
                _debug_print("Status HTTP da emissao com impostos explicitos", fallback_response.status_code)
                _debug_print("Body bruto da emissao com impostos explicitos", fallback_response.text)
                fallback_response.raise_for_status()
            except requests.RequestException as exc:
                retry_elapsed_ms = round((time.monotonic() - retry_started_at) * 1000, 2)
                fallback_error_message = build_webmania_request_exception_message(exc, default="Falha ao emitir Nota Fiscal de Serviço", scope="nfse")
                _debug_print("Falha HTTP na emissao com impostos explicitos", fallback_error_message)
                logger.warning("nfse_emission_retry_http_error", extra={"nfse_request_id": nfse_request.pk, "workshop_id": nfse_request.workshop.pk, "error": fallback_error_message, "duration_ms": retry_elapsed_ms})
                raise NfseEmissionError(fallback_error_message) from exc

            try:
                fallback_data = fallback_response.json()
            except ValueError as exc:
                _debug_print("Resposta da emissao com impostos explicitos nao e JSON", fallback_response.text)
                raise NfseEmissionError("Resposta inválida da API de emissão de Nota Fiscal de Serviço.") from exc

            _debug_print("JSON parseado da emissao com impostos explicitos", fallback_data)
            if not isinstance(fallback_data, dict):
                raise NfseEmissionError("Resposta inválida da API de emissão de Nota Fiscal de Serviço.")

            fallback_business_error = extract_webmania_error_message(
                fallback_data.get("error") or fallback_data.get("msg") or fallback_data.get("message"),
                scope="nfse",
            )
            if fallback_business_error:
                _debug_print("Erro de negocio na emissao com impostos explicitos", fallback_business_error)
                logger.warning(
                    "nfse_emission_retry_business_error nfse_request_id=%s workshop_id=%s error=%s",
                    getattr(nfse_request, "pk", None),
                    getattr(nfse_request.workshop, "pk", None),
                    fallback_business_error,
                )
                raise NfseEmissionError(fallback_business_error)

            if not fallback_data.get("modelo") and not fallback_data.get("uuid"):
                fallback_message = extract_webmania_error_message(fallback_data.get("msg") or fallback_data.get("message"), scope="nfse")
                if not fallback_message:
                    fallback_message = "Resposta da API sem modelo/uuid."
                _debug_print("Resposta sem dados esperados na emissao com impostos explicitos", fallback_data)
                raise NfseEmissionError(fallback_message)

            _debug_print(
                "Emissao de Nota Fiscal de Serviço aceita com impostos explicitos",
                {
                    "modelo": fallback_data.get("modelo"),
                    "status": fallback_data.get("status"),
                    "uuid": fallback_data.get("uuid"),
                    "motivo": fallback_data.get("motivo"),
                },
            )
            logger.info(
                "nfse_emission_retry_succeeded nfse_request_id=%s workshop_id=%s status=%s uuid=%s",
                getattr(nfse_request, "pk", None),
                getattr(nfse_request.workshop, "pk", None),
                str(fallback_data.get("status") or ""),
                str(fallback_data.get("uuid") or ""),
            )
            return fallback_data

        raise NfseEmissionError(error_message)

    if not data.get("modelo") and not data.get("uuid"):
        message = extract_webmania_error_message(data.get("msg") or data.get("message"), scope="nfse")
        if not message:
            message = "Resposta da API sem modelo/uuid."
        _debug_print("Resposta sem dados esperados de emissao", data)
        raise NfseEmissionError(message)

    _debug_print(
        "Emissao de Nota Fiscal de Serviço aceita",
        {
            "modelo": data.get("modelo"),
            "status": data.get("status"),
            "uuid": data.get("uuid"),
            "motivo": data.get("motivo"),
        },
    )
    logger.info("nfse_emission_succeeded", extra={"nfse_request_id": nfse_request.pk, "workshop_id": nfse_request.workshop.pk, "status": str(data.get("status") or ""), "uuid": str(data.get("uuid") or ""), "duration_ms": elapsed_ms})

    return data


def cancel_nfse_document(*, workshop, event_uuid: str, reason_code: int) -> dict[str, Any]:
    headers = _build_headers(workshop=workshop)
    cancel_url = _build_cancel_url()

    event_uuid_value = str(event_uuid or "").strip()
    if not event_uuid_value:
        raise NfseEmissionError("Nao foi possivel identificar a Nota Fiscal de Serviço para cancelamento.")

    try:
        motivo = int(reason_code)
    except (TypeError, ValueError) as exc:
        raise NfseEmissionError("Motivo de cancelamento invalido.") from exc

    if motivo not in {1, 2, 4}:
        raise NfseEmissionError("Motivo de cancelamento invalido.")

    payload = {"uuid": event_uuid_value, "motivo": motivo}

    try:
        response = requests.put(cancel_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = build_webmania_request_exception_message(exc, default="Falha ao cancelar Nota Fiscal de Serviço", scope="nfse")
        raise NfseEmissionError(message) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise NfseEmissionError("Resposta invalida da API de cancelamento de Nota Fiscal de Serviço.") from exc

    if not isinstance(data, dict):
        raise NfseEmissionError("Resposta invalida da API de cancelamento de Nota Fiscal de Serviço.")

    error_message = extract_webmania_error_message(data.get("error") or data.get("msg") or data.get("message"), scope="nfse")
    if error_message:
        raise NfseEmissionError(error_message)

    return data


def apply_nfse_batch_payload(
    *,
    batch: NfseBatch,
    response_payload: dict[str, Any],
    webhook_received_at=None,
) -> NfseBatch:
    mapped_batch = map_batch_payload(response_payload)
    for key, value in mapped_batch.items():
        if key == "uuid":
            continue
        setattr(batch, key, value)
    batch.raw_payload = response_payload
    if webhook_received_at is not None:
        batch.last_webhook_at = webhook_received_at
    batch.last_sync_error = ""
    batch.save()

    if batch.request:
        batch.request.update_status_based_on_request(response_payload.get("status"))

    return batch


def apply_nfse_item_payload(
    *,
    item: NfseItem,
    response_payload: dict[str, Any],
    webhook_received_at=None,
    reconciled_at=None,
) -> NfseItem:
    mapped_item = map_item_payload(response_payload)
    for key, value in mapped_item.items():
        if key == "uuid":
            continue
        setattr(item, key, value)
    item.raw_payload = response_payload
    if webhook_received_at is not None:
        item.last_webhook_at = webhook_received_at
    if reconciled_at is not None:
        item.last_reconciled_at = reconciled_at
    item.last_sync_error = ""
    item.save()

    if item.request:
        item.request.update_status_based_on_request(response_payload.get("status"))

    return item


def _replay_pending_nfse_webhooks_for_uuid(*, model: str, event_uuid: str) -> None:
    if not event_uuid:
        return

    from apps.core.infrastructure.services.webmania.webmania_webhooks import process_pending_webhook_events

    process_pending_webhook_events(model=model, event_uuid=event_uuid)


def sync_emission_response(*, nfse_request: NfseRequest, response_payload: dict[str, Any]) -> None:
    _debug_print("Iniciando sincronizacao da resposta", response_payload)
    logger.info("nfse_sync_started", extra={"nfse_request_id": nfse_request.pk, "workshop_id": nfse_request.workshop.pk, "model": str(response_payload.get("modelo") or "")})

    model = response_payload.get("modelo")
    if model not in {"lote_rps", "nfse"}:
        _debug_print("Modelo de resposta nao suportado para sincronizacao", model)
        logger.warning("nfse_sync_ignored_unsupported_model", extra={"nfse_request_id": nfse_request.pk, "workshop_id": nfse_request.workshop.pk, "model": str(model or "")})
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
                    "last_sync_error": "",
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
                if not str(item_payload.get("rps_number") or "").strip() and nfse_request.reserved_rps_number is not None:
                    item_payload["rps_number"] = str(nfse_request.reserved_rps_number)
                if not str(item_payload.get("rps_series") or "").strip() and str(nfse_request.reserved_rps_series or "").strip():
                    item_payload["rps_series"] = str(nfse_request.reserved_rps_series)
                if not str(item_payload.get("number") or "").strip() and nfse_request.reserved_rps_number is not None:
                    item_payload["number"] = str(nfse_request.reserved_rps_number)
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
                        "last_sync_error": "",
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
            logger.info("nfse_sync_batch_succeeded", extra={"nfse_request_id": nfse_request.pk, "workshop_id": nfse_request.workshop.pk, "batch_uuid": str(batch.uuid), "created_items": created_items, "updated_items": updated_items})

            _replay_pending_nfse_webhooks_for_uuid(model="lote_rps", event_uuid=str(batch.uuid))
            for item in batch.items.all():
                _replay_pending_nfse_webhooks_for_uuid(model="nfse", event_uuid=str(item.uuid))

            return

        mapped_item = map_item_payload(response_payload)
        if not str(mapped_item.get("rps_number") or "").strip() and nfse_request.reserved_rps_number is not None:
            mapped_item["rps_number"] = str(nfse_request.reserved_rps_number)
        if not str(mapped_item.get("rps_series") or "").strip() and str(nfse_request.reserved_rps_series or "").strip():
            mapped_item["rps_series"] = str(nfse_request.reserved_rps_series)
        if not str(mapped_item.get("number") or "").strip() and nfse_request.reserved_rps_number is not None:
            mapped_item["number"] = str(nfse_request.reserved_rps_number)
        item_uuid = mapped_item.pop("uuid", None)
        if not item_uuid:
            _debug_print("Nota Fiscal de Serviço sem UUID, sincronizacao ignorada", response_payload)
            return

        item, item_created = NfseItem.objects.update_or_create(
            workorder=nfse_request.workorder,
            uuid=item_uuid,
            defaults={
                "workshop": nfse_request.workshop,
                "request": nfse_request,
                "raw_payload": response_payload,
                "last_sync_error": "",
                **mapped_item,
            },
        )
        _debug_print(
            "Item de Nota Fiscal de Serviço sincronizado",
            {
                "uuid": str(item.uuid),
                "created": item_created,
                "status": item.status,
            },
        )
        logger.info("nfse_sync_item_succeeded", extra={"nfse_request_id": nfse_request.pk, "workshop_id": nfse_request.workshop.pk, "item_uuid": str(item.uuid), "created": item_created})

        _replay_pending_nfse_webhooks_for_uuid(model="nfse", event_uuid=str(item.uuid))
