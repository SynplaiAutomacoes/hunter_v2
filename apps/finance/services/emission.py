from __future__ import annotations

from copy import deepcopy
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

from apps.finance.models.finance import NfseBatch, NfseItem, NfseRequest
from apps.finance.services.mappers import extract_items_from_batch, map_batch_payload, map_item_payload
from apps.finance.services.pricing import build_slider_allocation_for_workorder
from apps.finance.services.webmania_auth import (
    WebmaniaAuthError,
    build_webmania_headers,
    redact_webmania_headers,
    sanitize_webmania_setting,
    should_use_global_webmania_auth,
)
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


def _is_padrao_nacional_tax_class(payload: dict[str, Any]) -> bool:
    model = str(payload.get("modelo") or payload.get("model") or "").strip().lower()
    if model == "padrao_nacional":
        return True

    pn_specific_fields = (
        "identificador_beneficio_municipal",
        "pis_cofins_retido",
        "data_competencia",
        "codigo_interno",
        "aliquota_tributos_aproximados",
        "codigo_nbs",
        "uf_local_prestacao",
        "cidade_local_prestacao",
    )
    if any(_has_payload_value(payload.get(field_name)) for field_name in pn_specific_fields):
        return True

    return _has_payload_value(payload.get("tributacao_iss")) and (_has_payload_value(payload.get("codigo_tributacao_municipio")) or _has_payload_value(payload.get("ibs_cbs")))


def _validate_tax_class_for_emission(*, nfse_request: NfseRequest, headers: dict[str, str]) -> dict[str, Any]:
    reference = str(nfse_request.tax_class or "").strip()
    if not reference:
        raise NfseEmissionError("Selecione uma classe de imposto para emitir a NFS-e.")

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
        raise NfseEmissionError("A classe de imposto selecionada não é do tipo NFS-e.")

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
    is_padrao_nacional = _is_padrao_nacional_tax_class(tax_class_payload)

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

    if is_padrao_nacional:
        for field_name in (
            "tipo_emissao",
            "natureza_operacao",
            "exigibilidade_iss",
            "iss_retido",
            "retencao_iss",
            "responsavel_retencao",
            "codigo_cnae",
            "retencao_pis_cofins",
        ):
            service_payload.pop(field_name, None)

    service_fields: tuple[str, ...]
    if is_padrao_nacional:
        service_fields = (
            "codigo_servico",
            "codigo_tributacao_municipio",
            "identificador_beneficio_municipal",
            "tributacao_iss",
            "tipo_imunidade",
            "pis_cofins_retido",
            "data_competencia",
            "codigo_nbs",
            "codigo_interno",
            "aliquota_tributos_aproximados",
            "uf_local_prestacao",
            "cidade_local_prestacao",
            "informacoes_complementares",
        )
    else:
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
            "identificador_beneficio_municipal",
            "pis_cofins_retido",
            "data_competencia",
            "codigo_interno",
            "finalidade",
            "consumidor_final",
            "cod_indicador_operacao",
            "codigo_nbs",
            "cidade_local_prestacao",
            "uf_local_prestacao",
            "aliquota_tributos_aproximados",
            "informacoes_complementares",
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
        legacy_retencao_iss = tax_class_payload.get("retencao_iss")
        if _has_payload_value(legacy_retencao_iss):
            service_payload["iss_retido"] = legacy_retencao_iss

    if not _has_payload_value(service_payload.get("pis_cofins_retido")):
        pis_cofins_retido = tax_class_payload.get("pis_cofins_retido")
        if not _has_payload_value(pis_cofins_retido):
            pis_cofins_retido = tax_class_payload.get("retencao_pis_cofins")
        if _has_payload_value(pis_cofins_retido):
            service_payload["pis_cofins_retido"] = pis_cofins_retido

    impostos_payload_raw = service_payload.get("impostos")
    impostos_payload = dict(impostos_payload_raw) if isinstance(impostos_payload_raw, dict) else {}
    if is_padrao_nacional:
        impostos_payload.pop("iss", None)

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
        if is_padrao_nacional and field_name == "iss":
            continue
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
            raise NfseEmissionError("Razão social do cliente é obrigatória para emissão da NFS-e com CNPJ.")

        return {
            "cnpj": customer.cpf_or_cnpj,
            "razao_social": razao_social,
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
    allocation = build_slider_allocation_for_workorder(workorder=nfse_request.workorder)
    amount = allocation.services_target.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if amount <= 0:
        raise NfseEmissionError("A OS selecionada nao possui saldo de servicos para emissao de NFS-e com a configuracao atual do slider.")

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

    logger.info(
        "nfse_payload_built nfse_request_id=%s workshop_id=%s workorder_id=%s tax_class=%s taker_type=%s",
        getattr(nfse_request, "pk", None),
        getattr(nfse_request.workshop, "pk", None),
        getattr(nfse_request.workorder, "pk", None),
        str(nfse_request.tax_class or ""),
        taker_type,
    )

    return payload


def emit_nfse_request(*, nfse_request: NfseRequest, request=None) -> dict[str, Any]:
    payload = build_nfse_payload(nfse_request=nfse_request, request=request)
    emit_url = _build_emit_url()
    headers = _build_headers(workshop=nfse_request.workshop)

    tax_class_payload = _validate_tax_class_for_emission(nfse_request=nfse_request, headers=headers)

    _debug_print(
        "Iniciando emissao de NFS-e",
        {
            "nfse_request_id": nfse_request.pk,
            "workorder_id": nfse_request.workorder.pk,
        },
    )
    logger.info(
        "nfse_emission_started nfse_request_id=%s workshop_id=%s workorder_id=%s",
        getattr(nfse_request, "pk", None),
        getattr(nfse_request.workshop, "pk", None),
        getattr(nfse_request.workorder, "pk", None),
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
        logger.warning(
            "nfse_emission_http_error nfse_request_id=%s workshop_id=%s error=%s",
            getattr(nfse_request, "pk", None),
            getattr(nfse_request.workshop, "pk", None),
            error_message,
        )
        raise NfseEmissionError(error_message) from exc

    try:
        data = response.json()
    except ValueError as exc:
        _debug_print("Resposta nao e JSON", response.text)
        raise NfseEmissionError("Resposta inválida da API de emissão de NFS-e.") from exc

    _debug_print("JSON parseado da emissao", data)

    if not isinstance(data, dict):
        raise NfseEmissionError("Resposta inválida da API de emissão de NFS-e.")

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
            logger.info(
                "nfse_emission_retry_with_explicit_tax_data nfse_request_id=%s workshop_id=%s",
                getattr(nfse_request, "pk", None),
                getattr(nfse_request.workshop, "pk", None),
            )

            try:
                fallback_response = requests.post(
                    emit_url,
                    json=fallback_payload,
                    headers=headers,
                    timeout=30,
                )
                _debug_print("Status HTTP da emissao com impostos explicitos", fallback_response.status_code)
                _debug_print("Body bruto da emissao com impostos explicitos", fallback_response.text)
                fallback_response.raise_for_status()
            except requests.RequestException as exc:
                fallback_error_message = build_webmania_request_exception_message(exc, default="Falha ao emitir NFS-e", scope="nfse")
                _debug_print("Falha HTTP na emissao com impostos explicitos", fallback_error_message)
                logger.warning(
                    "nfse_emission_retry_http_error nfse_request_id=%s workshop_id=%s error=%s",
                    getattr(nfse_request, "pk", None),
                    getattr(nfse_request.workshop, "pk", None),
                    fallback_error_message,
                )
                raise NfseEmissionError(fallback_error_message) from exc

            try:
                fallback_data = fallback_response.json()
            except ValueError as exc:
                _debug_print("Resposta da emissao com impostos explicitos nao e JSON", fallback_response.text)
                raise NfseEmissionError("Resposta inválida da API de emissão de NFS-e.") from exc

            _debug_print("JSON parseado da emissao com impostos explicitos", fallback_data)
            if not isinstance(fallback_data, dict):
                raise NfseEmissionError("Resposta inválida da API de emissão de NFS-e.")

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
                "Emissao de NFS-e aceita com impostos explicitos",
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
        "Emissao de NFS-e aceita",
        {
            "modelo": data.get("modelo"),
            "status": data.get("status"),
            "uuid": data.get("uuid"),
            "motivo": data.get("motivo"),
        },
    )
    logger.info(
        "nfse_emission_succeeded nfse_request_id=%s workshop_id=%s status=%s uuid=%s",
        getattr(nfse_request, "pk", None),
        getattr(nfse_request.workshop, "pk", None),
        str(data.get("status") or ""),
        str(data.get("uuid") or ""),
    )

    return data


def sync_emission_response(*, nfse_request: NfseRequest, response_payload: dict[str, Any]) -> None:
    _debug_print("Iniciando sincronizacao da resposta", response_payload)
    logger.info(
        "nfse_sync_started nfse_request_id=%s workshop_id=%s model=%s",
        getattr(nfse_request, "pk", None),
        getattr(nfse_request.workshop, "pk", None),
        str(response_payload.get("modelo") or ""),
    )

    model = response_payload.get("modelo")
    if model not in {"lote_rps", "nfse"}:
        _debug_print("Modelo de resposta nao suportado para sincronizacao", model)
        logger.warning(
            "nfse_sync_ignored_unsupported_model nfse_request_id=%s workshop_id=%s model=%s",
            getattr(nfse_request, "pk", None),
            getattr(nfse_request.workshop, "pk", None),
            str(model or ""),
        )
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
            logger.info(
                "nfse_sync_batch_succeeded nfse_request_id=%s workshop_id=%s batch_uuid=%s created_items=%s updated_items=%s",
                getattr(nfse_request, "pk", None),
                getattr(nfse_request.workshop, "pk", None),
                str(batch.uuid),
                created_items,
                updated_items,
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
        logger.info(
            "nfse_sync_item_succeeded nfse_request_id=%s workshop_id=%s item_uuid=%s created=%s",
            getattr(nfse_request, "pk", None),
            getattr(nfse_request.workshop, "pk", None),
            str(item.uuid),
            item_created,
        )
