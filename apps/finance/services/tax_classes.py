from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from django.conf import settings
from django.db import transaction

from apps.finance.models.finance import (
    TaxClassNfe,
    TaxClassNfeCofinsScenario,
    TaxClassNfeIcmsScenario,
    TaxClassNfeIpiScenario,
    TaxClassNfePisScenario,
    TaxClassNfse,
    TaxClassSyncState,
)
from apps.core.infrastructure.services.webmania.webmania_auth import (
    WebmaniaAuthError,
    build_webmania_headers,
    redact_webmania_headers,
    sanitize_webmania_setting,
    should_use_global_webmania_auth,
)
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message
from apps.finance.services.fiscal_attempts import sanitize_fiscal_payload
from apps.finance.services.ibs_cbs import IbsCbsConfigurationError, build_ibs_cbs_payload_from_values, build_tax_class_ibs_cbs_payload
from apps.workshops.models.workshops import Workshop


logger = logging.getLogger(__name__)

_SUCCESS_MESSAGE_KEYWORDS = (
    "sucesso",
    "atualizada com sucesso",
    "atualizado com sucesso",
    "classe de imposto atualizada",
    "classe de imposto atualizado",
    "criada com sucesso",
    "criado com sucesso",
    "classe de imposto criada",
    "classe de imposto criado",
    "salva com sucesso",
    "salvo com sucesso",
    "classe de imposto salva",
    "classe de imposto salvo",
)

_ERROR_MESSAGE_KEYWORDS = (
    "erro",
    "falha",
    "invál",
    "invalid",
    "obrigat",
    "não",
    "nao",
)


class TaxClassServiceError(Exception):
    pass


def _is_debug_enabled() -> bool:
    return bool(getattr(settings, "TAX_CLASS_DEBUG_LOGS", False))


def _debug_print(message: str, payload: Any | None = None) -> None:
    if not _is_debug_enabled():
        return

    if payload is None:
        logger.debug("tax_class_debug %s", message)
        return

    logger.debug("tax_class_debug %s payload=%s", message, sanitize_fiscal_payload(payload))


def _build_headers(*, workshop: Workshop) -> dict[str, str]:
    try:
        if should_use_global_webmania_auth():
            return build_webmania_headers()
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise TaxClassServiceError(str(exc)) from exc


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return redact_webmania_headers(headers)


def _build_tax_class_headers(*, workshop: Workshop) -> dict[str, str]:
    return _build_headers(workshop=workshop)


def _build_endpoint_url() -> str:
    custom_endpoint = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_ENDPOINT", ""))
    if custom_endpoint:
        endpoint = custom_endpoint.rstrip("/")
        return f"{endpoint}/"

    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return f"{base_url}/1/nfe/classe-imposto/"


def _extract_error_message(payload: Any) -> str:
    return extract_webmania_error_message(payload, scope="tax_class")


def _is_success_message(message: object) -> bool:
    normalized_message = str(message or "").strip().lower()
    if not normalized_message:
        return False
    if any(keyword in normalized_message for keyword in _ERROR_MESSAGE_KEYWORDS):
        return False
    return any(keyword in normalized_message for keyword in _SUCCESS_MESSAGE_KEYWORDS)


def _extract_tax_class_save_error_message(payload: dict[str, Any]) -> str:
    explicit_error = _extract_error_message(payload.get("error"))
    if explicit_error:
        return explicit_error

    message = _extract_error_message(payload.get("message") or payload.get("msg"))
    if message and not _is_success_message(message):
        return message

    return ""


def _parse_json_response(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise TaxClassServiceError("Resposta inválida da API de classe de imposto.") from exc


def _request_exception_message(exc: requests.RequestException, *, default: str) -> str:
    return build_webmania_request_exception_message(exc, default=default, scope="tax_class")


def _clean_string(value: Any) -> str:
    return str(value or "").strip()


def _digits_only(value: Any) -> str:
    raw_value = _clean_string(value)
    if not raw_value:
        return ""
    return "".join(char for char in raw_value if char.isdigit())


def _normalize_tax_type(payload: dict[str, Any]) -> str:
    return _clean_string(payload.get("tipo") or payload.get("type")).lower()


def _looks_like_nfse(payload: dict[str, Any]) -> bool:
    tax_type = _normalize_tax_type(payload)
    if tax_type in {"nfse", "nfs-e", "nsfe"}:
        return True
    return bool(_clean_string(payload.get("tipo_emissao"))) and bool(_clean_string(payload.get("codigo_servico")))


def _normalize_tax_class_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized_payload = dict(payload)

    reference = _clean_string(normalized_payload.get("referencia"))
    if reference:
        normalized_payload["referencia"] = reference

    description = _clean_string(normalized_payload.get("descricao"))
    if description:
        normalized_payload["descricao"] = description

    status = _clean_string(normalized_payload.get("status"))
    if status:
        normalized_payload["status"] = status

    remote_date = _clean_string(normalized_payload.get("data"))
    if remote_date:
        normalized_payload["data"] = remote_date

    remote_updated_date = _clean_string(normalized_payload.get("updated_date"))
    if remote_updated_date:
        normalized_payload["updated_date"] = remote_updated_date

    tax_type = _normalize_tax_type(normalized_payload)
    if tax_type:
        normalized_payload["tipo"] = tax_type
        normalized_payload["type"] = tax_type

    return normalized_payload


NFSE_CODIGO_SERVICO_HELP_TEXT = "ABRASF: XX.XX ou XXXXX. Padrão Nacional: XX.XX.XX ou XXXXXX (6 dígitos)."
NFSE_CODIGO_SERVICO_INVALID_FORMAT = "Informe o código do serviço no formato XX.XX, XXXXX, XX.XX.XX ou XXXXXX."
NFSE_CODIGO_SERVICO_NATIONAL_LENGTH_ERROR = (
    "Para este município o código do serviço precisa ter 6 dígitos no formato XX.XX.XX (ex.: 01.05.01). "
    "O valor informado tem formato incompleto para o Padrão Nacional."
)


def format_nfse_service_code_for_api(value: Any) -> str:
    raw_value = _clean_string(value)
    code_digits = _digits_only(raw_value)
    if len(code_digits) == 4:
        return f"{code_digits[:2]}.{code_digits[2:]}"
    if len(code_digits) == 6:
        return f"{code_digits[:2]}.{code_digits[2:4]}.{code_digits[4:]}"
    return raw_value


def _format_nfse_service_code_for_api(value: Any) -> str:
    return format_nfse_service_code_for_api(value)


def is_valid_nfse_service_code(value: str) -> bool:
    if not value:
        return False
    if len(value) == 5 and value[2] == "." and value.replace(".", "").isdigit() and len(value.replace(".", "")) == 4:
        return True
    if len(value) == 5 and value.isdigit():
        return True
    if len(value) == 8 and value[2] == "." and value[5] == "." and value.replace(".", "").isdigit() and len(value.replace(".", "")) == 6:
        return True
    if len(value) == 6 and value.isdigit():
        return True
    return False


def map_nfse_codigo_servico_api_error(message: object) -> str | None:
    normalized_message = str(message or "").strip().lower()
    if "codigo_servico" in normalized_message and "6 caracteres" in normalized_message:
        return NFSE_CODIGO_SERVICO_NATIONAL_LENGTH_ERROR
    return None


def _normalize_payload_for_api(payload: dict[str, Any]) -> dict[str, Any]:
    normalized_payload = dict(payload)
    if _looks_like_nfse(normalized_payload):
        service_code = normalized_payload.get("codigo_servico")
        if service_code not in (None, ""):
            normalized_payload["codigo_servico"] = format_nfse_service_code_for_api(service_code)
    return normalized_payload


def _normalize_scenarios(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized_items: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            normalized_items.append(dict(item))
    return normalized_items


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None

    normalized_value = str(value).strip().replace(",", ".")
    if not normalized_value:
        return None

    try:
        return Decimal(normalized_value)
    except (InvalidOperation, ValueError):
        return None


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    return f"{value.quantize(Decimal('0.01')):f}"


def _extract_ibs_cbs_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    try:
        return build_ibs_cbs_payload_from_values(
            enabled=True,
            situacao_tributaria=str(value.get("situacao_tributaria") or ""),
            classificacao_tributaria=str(value.get("classificacao_tributaria") or ""),
            situacao_tributaria_regular=str(value.get("situacao_tributaria_regular") or ""),
            classificacao_tributaria_regular=str(value.get("classificacao_tributaria_regular") or ""),
            details={key: item for key, item in value.items() if key not in {"situacao_tributaria", "classificacao_tributaria", "situacao_tributaria_regular", "classificacao_tributaria_regular"}},
        )
    except IbsCbsConfigurationError as exc:
        raise TaxClassServiceError(str(exc)) from exc


def _to_bool_or_none(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value

    normalized_value = str(value).strip().lower()
    if normalized_value in {"1", "true", "yes", "sim"}:
        return True
    if normalized_value in {"0", "false", "no", "nao", "não"}:
        return False
    return None


def _serialize_icms_scenarios(tax_class: TaxClassNfe) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for scenario in getattr(tax_class, "icms_scenarios").all():
        item: dict[str, Any] = {}
        if scenario.tipo_tributacao:
            item["tipo_tributacao"] = scenario.tipo_tributacao
        if scenario.cenario:
            item["cenario"] = scenario.cenario
        if scenario.tipo_pessoa:
            item["tipo_pessoa"] = scenario.tipo_pessoa
        if scenario.nao_contribuinte is not None:
            item["nao_contribuinte"] = bool(scenario.nao_contribuinte)
        if scenario.codigo_cfop:
            item["codigo_cfop"] = scenario.codigo_cfop
        if scenario.situacao_tributaria:
            item["situacao_tributaria"] = scenario.situacao_tributaria
        if scenario.aliquota_credito is not None:
            item["aliquota_credito"] = _format_decimal(scenario.aliquota_credito)
        if scenario.aliquota_importacao is not None:
            item["aliquota_importacao"] = _format_decimal(scenario.aliquota_importacao)
        if item:
            payloads.append(item)
    return payloads


def _serialize_ipi_scenarios(tax_class: TaxClassNfe) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for scenario in getattr(tax_class, "ipi_scenarios").all():
        item: dict[str, Any] = {}
        if scenario.cenario:
            item["cenario"] = scenario.cenario
        if scenario.tipo_pessoa:
            item["tipo_pessoa"] = scenario.tipo_pessoa
        if scenario.situacao_tributaria:
            item["situacao_tributaria"] = scenario.situacao_tributaria
        if scenario.codigo_enquadramento:
            item["codigo_enquadramento"] = scenario.codigo_enquadramento
        if scenario.aliquota is not None:
            item["aliquota"] = _format_decimal(scenario.aliquota)
        if item:
            payloads.append(item)
    return payloads


def _serialize_pis_scenarios(tax_class: TaxClassNfe) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for scenario in getattr(tax_class, "pis_scenarios").all():
        item: dict[str, Any] = {}
        if scenario.cenario:
            item["cenario"] = scenario.cenario
        if scenario.tipo_pessoa:
            item["tipo_pessoa"] = scenario.tipo_pessoa
        if scenario.situacao_tributaria:
            item["situacao_tributaria"] = scenario.situacao_tributaria
        if scenario.aliquota is not None:
            item["aliquota"] = _format_decimal(scenario.aliquota)
        if item:
            payloads.append(item)
    return payloads


def _serialize_cofins_scenarios(tax_class: TaxClassNfe) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for scenario in getattr(tax_class, "cofins_scenarios").all():
        item: dict[str, Any] = {}
        if scenario.cenario:
            item["cenario"] = scenario.cenario
        if scenario.tipo_pessoa:
            item["tipo_pessoa"] = scenario.tipo_pessoa
        if scenario.situacao_tributaria:
            item["situacao_tributaria"] = scenario.situacao_tributaria
        if scenario.aliquota is not None:
            item["aliquota"] = _format_decimal(scenario.aliquota)
        if item:
            payloads.append(item)
    return payloads


def _replace_icms_scenarios(*, tax_class: TaxClassNfe, items: list[dict[str, Any]]) -> None:
    TaxClassNfeIcmsScenario.objects.filter(tax_class=tax_class).delete()
    if not items:
        return

    instances = [
        TaxClassNfeIcmsScenario(
            tax_class=tax_class,
            position=index,
            tipo_tributacao=_clean_string(item.get("tipo_tributacao")),
            cenario=_clean_string(item.get("cenario")),
            tipo_pessoa=_clean_string(item.get("tipo_pessoa")),
            nao_contribuinte=_to_bool_or_none(item.get("nao_contribuinte")),
            codigo_cfop=_clean_string(item.get("codigo_cfop")),
            situacao_tributaria=_clean_string(item.get("situacao_tributaria")),
            aliquota_credito=_to_decimal(item.get("aliquota_credito")),
            aliquota_importacao=_to_decimal(item.get("aliquota_importacao")),
        )
        for index, item in enumerate(items)
    ]
    TaxClassNfeIcmsScenario.objects.bulk_create(instances)


def _replace_ipi_scenarios(*, tax_class: TaxClassNfe, items: list[dict[str, Any]]) -> None:
    TaxClassNfeIpiScenario.objects.filter(tax_class=tax_class).delete()
    if not items:
        return

    instances = [
        TaxClassNfeIpiScenario(
            tax_class=tax_class,
            position=index,
            cenario=_clean_string(item.get("cenario")),
            tipo_pessoa=_clean_string(item.get("tipo_pessoa")),
            situacao_tributaria=_clean_string(item.get("situacao_tributaria")),
            codigo_enquadramento=_clean_string(item.get("codigo_enquadramento")),
            aliquota=_to_decimal(item.get("aliquota")),
        )
        for index, item in enumerate(items)
    ]
    TaxClassNfeIpiScenario.objects.bulk_create(instances)


def _replace_pis_scenarios(*, tax_class: TaxClassNfe, items: list[dict[str, Any]]) -> None:
    TaxClassNfePisScenario.objects.filter(tax_class=tax_class).delete()
    if not items:
        return

    instances = [
        TaxClassNfePisScenario(
            tax_class=tax_class,
            position=index,
            cenario=_clean_string(item.get("cenario")),
            tipo_pessoa=_clean_string(item.get("tipo_pessoa")),
            situacao_tributaria=_clean_string(item.get("situacao_tributaria")),
            aliquota=_to_decimal(item.get("aliquota")),
        )
        for index, item in enumerate(items)
    ]
    TaxClassNfePisScenario.objects.bulk_create(instances)


def _replace_cofins_scenarios(*, tax_class: TaxClassNfe, items: list[dict[str, Any]]) -> None:
    TaxClassNfeCofinsScenario.objects.filter(tax_class=tax_class).delete()
    if not items:
        return

    instances = [
        TaxClassNfeCofinsScenario(
            tax_class=tax_class,
            position=index,
            cenario=_clean_string(item.get("cenario")),
            tipo_pessoa=_clean_string(item.get("tipo_pessoa")),
            situacao_tributaria=_clean_string(item.get("situacao_tributaria")),
            aliquota=_to_decimal(item.get("aliquota")),
        )
        for index, item in enumerate(items)
    ]
    TaxClassNfeCofinsScenario.objects.bulk_create(instances)


def _serialize_nfe_tax_class(tax_class: TaxClassNfe) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "referencia": tax_class.reference,
        "descricao": tax_class.description,
        "tipo": "nfe",
        "type": "nfe",
        "status": tax_class.status,
        "data": tax_class.remote_date,
    }

    if tax_class.remote_updated_date:
        payload["updated_date"] = tax_class.remote_updated_date
    if tax_class.informacoes_fisco:
        payload["informacoes_fisco"] = tax_class.informacoes_fisco
    if tax_class.informacoes_complementares:
        payload["informacoes_complementares"] = tax_class.informacoes_complementares

    icms_payload = _serialize_icms_scenarios(tax_class)
    ipi_payload = _serialize_ipi_scenarios(tax_class)
    pis_payload = _serialize_pis_scenarios(tax_class)
    cofins_payload = _serialize_cofins_scenarios(tax_class)

    if icms_payload:
        payload["icms"] = icms_payload
    if ipi_payload:
        payload["ipi"] = ipi_payload
    if pis_payload:
        payload["pis"] = pis_payload
    if cofins_payload:
        payload["cofins"] = cofins_payload
    try:
        ibs_cbs_payload = build_tax_class_ibs_cbs_payload(tax_class)
    except IbsCbsConfigurationError:
        ibs_cbs_payload = {}
    if ibs_cbs_payload:
        payload["ibs_cbs"] = ibs_cbs_payload

    return payload


def _serialize_nfse_tax_class(tax_class: TaxClassNfse) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "referencia": tax_class.reference,
        "descricao": tax_class.description,
        "tipo": "nfse",
        "type": "nfse",
        "status": tax_class.status,
        "data": tax_class.remote_date,
    }

    if tax_class.remote_updated_date:
        payload["updated_date"] = tax_class.remote_updated_date
    if tax_class.informacoes_fisco:
        payload["informacoes_fisco"] = tax_class.informacoes_fisco
    if tax_class.informacoes_complementares:
        payload["informacoes_complementares"] = tax_class.informacoes_complementares

    text_fields = (
        "tipo_emissao",
        "codigo_servico",
        "codigo_tributacao_municipio",
        "tributacao_iss",
        "tipo_imunidade",
        "retencao_iss",
        "cst_pis_cofins",
        "retencao_pis_cofins",
        "natureza_operacao",
        "exigibilidade_iss",
        "iss_retido",
        "responsavel_retencao",
        "codigo_cnae",
    )
    for field_name in text_fields:
        value = _clean_string(getattr(tax_class, field_name))
        if value:
            payload[field_name] = value

    for field_name in ("iss", "pis", "cofins", "inss", "ir", "csll"):
        value = getattr(tax_class, field_name)
        if value is not None:
            payload[field_name] = _format_decimal(value)

    ibs_cbs: dict[str, Any] = {}
    if tax_class.ibs_situacao_tributaria:
        ibs_cbs["situacao_tributaria"] = tax_class.ibs_situacao_tributaria
    if tax_class.ibs_classificacao_tributaria:
        ibs_cbs["classificacao_tributaria"] = tax_class.ibs_classificacao_tributaria
    if tax_class.ibs_situacao_tributaria_regular:
        ibs_cbs["situacao_tributaria_regular"] = tax_class.ibs_situacao_tributaria_regular
    if tax_class.ibs_classificacao_tributaria_regular:
        ibs_cbs["classificacao_tributaria_regular"] = tax_class.ibs_classificacao_tributaria_regular
    if tax_class.ibs_credito_presumido:
        ibs_cbs["credito_presumido"] = tax_class.ibs_credito_presumido
    if tax_class.ibs_aliquota_diferimento_estadual is not None:
        ibs_cbs["ibs_estadual"] = {"aliquota_diferimento": float(tax_class.ibs_aliquota_diferimento_estadual)}
    if tax_class.ibs_aliquota_diferimento_municipal is not None:
        ibs_cbs["ibs_municipal"] = {"aliquota_diferimento": float(tax_class.ibs_aliquota_diferimento_municipal)}
    if tax_class.cbs_aliquota_diferimento is not None:
        ibs_cbs["cbs"] = {"aliquota_diferimento": float(tax_class.cbs_aliquota_diferimento)}
    if ibs_cbs:
        payload["ibs_cbs"] = ibs_cbs

    return payload


def _upsert_local_nfe_tax_class(*, workshop: Workshop, payload: dict[str, Any]) -> dict[str, Any]:
    reference = _clean_string(payload.get("referencia"))
    if not reference:
        raise TaxClassServiceError("Classe de imposto sem referência não pode ser salva localmente.")

    ibs_cbs = _extract_ibs_cbs_payload(payload.get("ibs_cbs"))
    ibs_cbs_enabled = bool(ibs_cbs)
    ibs_cbs_details = {key: value for key, value in ibs_cbs.items() if key not in {"situacao_tributaria", "classificacao_tributaria", "situacao_tributaria_regular", "classificacao_tributaria_regular"}}

    with transaction.atomic():
        tax_class, _ = TaxClassNfe.objects.update_or_create(
            workshop=workshop,
            reference=reference,
            defaults={
                "description": _clean_string(payload.get("descricao")),
                "status": _clean_string(payload.get("status")),
                "remote_date": _clean_string(payload.get("data")),
                "remote_updated_date": _clean_string(payload.get("updated_date")),
                "informacoes_fisco": _clean_string(payload.get("informacoes_fisco")),
                "informacoes_complementares": _clean_string(payload.get("informacoes_complementares")),
                "ibs_cbs_enabled": ibs_cbs_enabled,
                "ibs_cbs_situacao_tributaria": _clean_string(ibs_cbs.get("situacao_tributaria"))[:3],
                "ibs_cbs_classificacao_tributaria": _clean_string(ibs_cbs.get("classificacao_tributaria"))[:6],
                "ibs_cbs_situacao_tributaria_regular": _clean_string(ibs_cbs.get("situacao_tributaria_regular"))[:3],
                "ibs_cbs_classificacao_tributaria_regular": _clean_string(ibs_cbs.get("classificacao_tributaria_regular"))[:6],
                "ibs_cbs_details": ibs_cbs_details,
            },
        )

        _replace_icms_scenarios(tax_class=tax_class, items=_normalize_scenarios(payload.get("icms")))
        _replace_ipi_scenarios(tax_class=tax_class, items=_normalize_scenarios(payload.get("ipi")))
        _replace_pis_scenarios(tax_class=tax_class, items=_normalize_scenarios(payload.get("pis")))
        _replace_cofins_scenarios(tax_class=tax_class, items=_normalize_scenarios(payload.get("cofins")))

    TaxClassNfse.objects.filter(workshop=workshop, reference=reference).delete()
    return _serialize_nfe_tax_class(tax_class)


def _upsert_local_nfse_tax_class(*, workshop: Workshop, payload: dict[str, Any]) -> dict[str, Any]:
    reference = _clean_string(payload.get("referencia"))
    if not reference:
        raise TaxClassServiceError("Classe de imposto sem referência não pode ser salva localmente.")

    ibs_cbs_raw = payload.get("ibs_cbs")
    ibs_cbs: dict[str, Any] = dict(ibs_cbs_raw) if isinstance(ibs_cbs_raw, dict) else {}
    ibs_estadual_raw = ibs_cbs.get("ibs_estadual")
    ibs_estadual: dict[str, Any] = dict(ibs_estadual_raw) if isinstance(ibs_estadual_raw, dict) else {}
    ibs_municipal_raw = ibs_cbs.get("ibs_municipal")
    ibs_municipal: dict[str, Any] = dict(ibs_municipal_raw) if isinstance(ibs_municipal_raw, dict) else {}
    cbs_raw = ibs_cbs.get("cbs")
    cbs: dict[str, Any] = dict(cbs_raw) if isinstance(cbs_raw, dict) else {}

    tax_class, _ = TaxClassNfse.objects.update_or_create(
        workshop=workshop,
        reference=reference,
        defaults={
            "description": _clean_string(payload.get("descricao")),
            "status": _clean_string(payload.get("status")),
            "remote_date": _clean_string(payload.get("data")),
            "remote_updated_date": _clean_string(payload.get("updated_date")),
            "informacoes_fisco": _clean_string(payload.get("informacoes_fisco")),
            "informacoes_complementares": _clean_string(payload.get("informacoes_complementares")),
            "tipo_emissao": _clean_string(payload.get("tipo_emissao")),
            "codigo_servico": _format_nfse_service_code_for_api(payload.get("codigo_servico")),
            "codigo_tributacao_municipio": _clean_string(payload.get("codigo_tributacao_municipio")),
            "tributacao_iss": _clean_string(payload.get("tributacao_iss")),
            "tipo_imunidade": _clean_string(payload.get("tipo_imunidade")),
            "retencao_iss": _clean_string(payload.get("retencao_iss") or payload.get("iss_retido")),
            "cst_pis_cofins": _clean_string(payload.get("cst_pis_cofins")),
            "retencao_pis_cofins": _clean_string(payload.get("retencao_pis_cofins")),
            "natureza_operacao": _clean_string(payload.get("natureza_operacao")),
            "exigibilidade_iss": _clean_string(payload.get("exigibilidade_iss")),
            "iss_retido": _clean_string(payload.get("iss_retido") or payload.get("retencao_iss")),
            "responsavel_retencao": _clean_string(payload.get("responsavel_retencao")),
            "codigo_cnae": _clean_string(payload.get("codigo_cnae")),
            "iss": _to_decimal(payload.get("iss")),
            "pis": _to_decimal(payload.get("pis")),
            "cofins": _to_decimal(payload.get("cofins")),
            "inss": _to_decimal(payload.get("inss")),
            "ir": _to_decimal(payload.get("ir")),
            "csll": _to_decimal(payload.get("csll")),
            "ibs_situacao_tributaria": _clean_string(ibs_cbs.get("situacao_tributaria")),
            "ibs_classificacao_tributaria": _clean_string(ibs_cbs.get("classificacao_tributaria")),
            "ibs_situacao_tributaria_regular": _clean_string(ibs_cbs.get("situacao_tributaria_regular")),
            "ibs_classificacao_tributaria_regular": _clean_string(ibs_cbs.get("classificacao_tributaria_regular")),
            "ibs_credito_presumido": _clean_string(ibs_cbs.get("credito_presumido")),
            "ibs_aliquota_diferimento_estadual": _to_decimal(ibs_estadual.get("aliquota_diferimento")),
            "ibs_aliquota_diferimento_municipal": _to_decimal(ibs_municipal.get("aliquota_diferimento")),
            "cbs_aliquota_diferimento": _to_decimal(cbs.get("aliquota_diferimento")),
        },
    )
    TaxClassNfe.objects.filter(workshop=workshop, reference=reference).delete()
    return _serialize_nfse_tax_class(tax_class)


def _upsert_local_tax_class(*, workshop: Workshop, payload: dict[str, Any]) -> dict[str, Any]:
    normalized_payload = _normalize_tax_class_payload(payload)
    if _looks_like_nfse(normalized_payload):
        return _upsert_local_nfse_tax_class(workshop=workshop, payload=normalized_payload)
    return _upsert_local_nfe_tax_class(workshop=workshop, payload=normalized_payload)


def _upsert_local_tax_classes(*, workshop: Workshop, tax_classes: list[dict[str, Any]]) -> None:
    for item in tax_classes:
        reference = _clean_string(item.get("referencia"))
        if not reference:
            continue
        _upsert_local_tax_class(workshop=workshop, payload=item)


def _replace_local_tax_classes(*, workshop: Workshop, tax_classes: list[dict[str, Any]]) -> None:
    references: set[str] = set()
    for item in tax_classes:
        if not isinstance(item, dict):
            continue
        reference = _clean_string(item.get("referencia"))
        if reference:
            references.add(reference)

    if references:
        TaxClassNfe.objects.filter(workshop=workshop).exclude(reference__in=references).delete()
        TaxClassNfse.objects.filter(workshop=workshop).exclude(reference__in=references).delete()

    _upsert_local_tax_classes(workshop=workshop, tax_classes=tax_classes)


def _list_local_tax_classes(*, workshop: Workshop) -> list[dict[str, Any]]:
    nfe_tax_classes = TaxClassNfe.objects.filter(workshop=workshop).prefetch_related("icms_scenarios", "ipi_scenarios", "pis_scenarios", "cofins_scenarios")
    nfse_tax_classes = TaxClassNfse.objects.filter(workshop=workshop)

    payloads: list[dict[str, Any]] = []
    payloads.extend(_serialize_nfe_tax_class(item) for item in nfe_tax_classes)
    payloads.extend(_serialize_nfse_tax_class(item) for item in nfse_tax_classes)
    return payloads


def _list_tax_classes_remote(*, workshop: Workshop) -> list[dict[str, Any]]:
    endpoint = _build_endpoint_url()
    headers = _build_tax_class_headers(workshop=workshop)

    _debug_print("GET endpoint", endpoint)
    _debug_print("GET headers", _redact_headers(headers))

    try:
        response = requests.get(endpoint, headers=headers, timeout=30)
        _debug_print("GET status", response.status_code)
        _debug_print("GET body", response.text)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = _request_exception_message(exc, default="Falha ao listar classes de imposto")
        raise TaxClassServiceError(message) from exc

    payload = _parse_json_response(response)
    if not isinstance(payload, list):
        extracted = _extract_error_message(payload)
        if extracted:
            raise TaxClassServiceError(extracted)
        raise TaxClassServiceError("Resposta inválida da API ao listar classes de imposto.")

    return [item for item in payload if isinstance(item, dict)]


def _mark_initial_sync_done(*, workshop: Workshop) -> None:
    TaxClassSyncState.objects.update_or_create(workshop=workshop, defaults={"synced_once": True})


def _merge_tax_class_payloads(*, sent_payload: dict[str, Any], response_payload: dict[str, Any]) -> dict[str, Any]:
    merged_payload = dict(sent_payload)
    merged_payload.update(response_payload)
    return _normalize_tax_class_payload(merged_payload)


def list_tax_classes(*, workshop: Workshop, force_refresh: bool = False) -> list[dict[str, Any]]:
    if force_refresh:
        return sync_tax_classes(workshop=workshop)

    return _list_local_tax_classes(workshop=workshop)


def sync_tax_classes(*, workshop: Workshop) -> list[dict[str, Any]]:
    remote_tax_classes = _list_tax_classes_remote(workshop=workshop)
    _replace_local_tax_classes(workshop=workshop, tax_classes=remote_tax_classes)
    _mark_initial_sync_done(workshop=workshop)
    return _list_local_tax_classes(workshop=workshop)


def save_tax_class(*, workshop: Workshop, payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        raise TaxClassServiceError("Informe o payload da classe de imposto.")

    normalized_payload = _normalize_payload_for_api(payload)
    endpoint = _build_endpoint_url()
    headers = _build_tax_class_headers(workshop=workshop)

    try:
        response = requests.post(endpoint, json=normalized_payload, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = _request_exception_message(exc, default="Falha ao salvar classe de imposto")
        logger.exception("Erro ao salvar classe de imposto", extra={"workshop_id": getattr(workshop, "pk", None)})
        raise TaxClassServiceError(message) from exc

    data = _parse_json_response(response)
    if not isinstance(data, dict):
        raise TaxClassServiceError("Resposta inválida da API ao salvar classe de imposto.")

    error_message = _extract_tax_class_save_error_message(data)
    if error_message:
        raise TaxClassServiceError(error_message)

    merged_payload = _merge_tax_class_payloads(sent_payload=normalized_payload, response_payload=data)
    saved_payload = _upsert_local_tax_class(workshop=workshop, payload=merged_payload)
    _mark_initial_sync_done(workshop=workshop)
    return saved_payload


def delete_tax_class(*, workshop: Workshop, reference: str | list[str]) -> list[dict[str, Any]]:
    if isinstance(reference, str):
        normalized_reference = reference.strip()
        if not normalized_reference:
            raise TaxClassServiceError("Informe a referencia da classe de imposto para excluir.")
        payload_reference: str | list[str] = normalized_reference
        references_to_delete = [normalized_reference]
    else:
        references = [item.strip() for item in reference if isinstance(item, str) and item.strip()]
        if not references:
            raise TaxClassServiceError("Informe ao menos uma referencia válida para excluir.")
        payload_reference = references
        references_to_delete = references

    endpoint = _build_endpoint_url()
    headers = _build_tax_class_headers(workshop=workshop)
    delete_payload = {"referencia": payload_reference}

    _debug_print("DELETE endpoint", endpoint)
    _debug_print("DELETE headers", _redact_headers(headers))
    _debug_print("DELETE payload", delete_payload)

    try:
        response = requests.delete(endpoint, json=delete_payload, headers=headers, timeout=30)
        _debug_print("DELETE status", response.status_code)
        _debug_print("DELETE body", response.text)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = _request_exception_message(exc, default="Falha ao excluir classe de imposto")
        _debug_print("DELETE request exception", message)
        raise TaxClassServiceError(message) from exc

    data = _parse_json_response(response)
    if not isinstance(data, list):
        if isinstance(data, dict):
            error_message = _extract_error_message(data.get("error") or data.get("message") or data.get("msg"))
            if error_message:
                raise TaxClassServiceError(error_message)
        raise TaxClassServiceError("Resposta inválida da API ao excluir classe de imposto.")

    for item in data:
        if not isinstance(item, dict):
            continue
        error_message = _extract_error_message(item.get("error") or item.get("message") or item.get("msg"))
        if error_message and "sucesso" not in error_message.lower():
            raise TaxClassServiceError(error_message)

    TaxClassNfe.objects.filter(workshop=workshop, reference__in=references_to_delete).delete()
    TaxClassNfse.objects.filter(workshop=workshop, reference__in=references_to_delete).delete()
    _mark_initial_sync_done(workshop=workshop)
    return [item for item in data if isinstance(item, dict)]
