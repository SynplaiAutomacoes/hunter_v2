from __future__ import annotations

from typing import Any

import requests
from django.conf import settings
from django.utils import timezone

from apps.finance.models import WebmaniaCompany, WebmaniaCompanyTaxType
from apps.finance.services.webmania_auth import (
    WebmaniaAuthError,
    build_webmania_b2b_headers,
    build_webmania_headers_for_company,
    sanitize_webmania_setting,
)
from apps.finance.services.webmania_secrets import encrypt_secret
from apps.workshops.models.workshops import Workshop


class WebmaniaB2BServiceError(Exception):
    pass


_SENSITIVE_COMPANY_FIELDS = (
    "consumer_key",
    "consumer_secret",
    "access_token",
    "access_token_secret",
    "bearer_access_token",
)


def _build_base_url() -> str:
    base_url = sanitize_webmania_setting(getattr(settings, "WEBMANIA_B2B_BASE_URL", "https://webmania.com.br/api")).rstrip("/")
    return base_url


def _build_companies_url() -> str:
    return f"{_build_base_url()}/1/b2b/empresas/"


def _build_requests_url() -> str:
    return f"{_build_base_url()}/1/b2b/requests/"


def _build_nfe_company_url() -> str:
    return "https://webmania.com.br/api/1/nfe/empresa/"


def _extract_error_message(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()

    if isinstance(payload, dict):
        for key in ("error", "message", "msg", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return ""


def _request_exception_message(exc: requests.RequestException, *, default: str) -> str:
    if exc.response is None:
        return f"{default}: {exc}"

    payload: Any | None
    try:
        payload = exc.response.json()
    except ValueError:
        payload = exc.response.text

    extracted = _extract_error_message(payload)
    if extracted:
        return extracted

    response_text = str(exc.response.text or "").strip()
    if response_text:
        return f"{default}: {response_text}"

    return f"{default}: {exc}"


def _parse_json_response(response: requests.Response, *, error_message: str) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise WebmaniaB2BServiceError(error_message) from exc


def _build_headers() -> dict[str, str]:
    try:
        return build_webmania_b2b_headers()
    except WebmaniaAuthError as exc:
        raise WebmaniaB2BServiceError(str(exc)) from exc


def _build_company_headers(company: WebmaniaCompany) -> dict[str, str]:
    try:
        return build_webmania_headers_for_company(company)
    except WebmaniaAuthError as exc:
        raise WebmaniaB2BServiceError(str(exc)) from exc


def _clean_string(value: object) -> str:
    return str(value or "").strip()


def _normalize_tax_type(value: object) -> str:
    normalized = _clean_string(value).lower()
    if normalized in {WebmaniaCompanyTaxType.SIMPLES_NACIONAL, WebmaniaCompanyTaxType.LUCRO_NORMAL}:
        return normalized
    return ""


def _extract_credentials(payload: dict[str, Any]) -> dict[str, str]:
    credentials_raw = payload.get("credenciais")
    credentials = credentials_raw if isinstance(credentials_raw, dict) else payload

    return {
        "consumer_key": _clean_string(credentials.get("consumer_key")),
        "consumer_secret": _clean_string(credentials.get("consumer_secret")),
        "access_token": _clean_string(credentials.get("access_token")),
        "access_token_secret": _clean_string(credentials.get("access_token_secret")),
        "bearer_access_token": _clean_string(credentials.get("bearer_access_token")),
    }


def _upsert_company_from_payload(*, payload: dict[str, Any], workshop: Workshop | None = None) -> WebmaniaCompany | None:
    company_id = _clean_string(payload.get("id"))
    if not company_id:
        return None

    company = WebmaniaCompany.objects.filter(webmania_company_id=company_id).first()
    if company is None and workshop is not None:
        company = WebmaniaCompany.objects.filter(workshop=workshop).first()
    if company is None:
        company = WebmaniaCompany(webmania_company_id=company_id)

    company.webmania_company_id = company_id
    if workshop is not None:
        company.workshop = workshop

    credentials = _extract_credentials(payload)
    for field_name in _SENSITIVE_COMPANY_FIELDS:
        raw_value = credentials.get(field_name)
        if raw_value:
            setattr(company, field_name, encrypt_secret(raw_value))

    if "cnpj" in payload:
        company.cnpj = _clean_string(payload.get("cnpj"))
    if "razao_social" in payload:
        company.razao_social = _clean_string(payload.get("razao_social"))
    if "cpf" in payload:
        company.cpf = _clean_string(payload.get("cpf"))
    if "nome_completo" in payload:
        company.nome_completo = _clean_string(payload.get("nome_completo"))
    if "ie" in payload:
        company.ie = _clean_string(payload.get("ie"))
    if "cidade" in payload:
        company.cidade = _clean_string(payload.get("cidade"))
    if "estado" in payload or "uf" in payload:
        company.uf = _clean_string(payload.get("estado") or payload.get("uf"))
    if "unidade_empresa" in payload:
        company.unidade_empresa = _clean_string(payload.get("unidade_empresa"))
    if "tipo_tributacao" in payload:
        company.tipo_tributacao = _normalize_tax_type(payload.get("tipo_tributacao"))
    company.last_sync_at = timezone.now()
    company.last_sync_error = ""
    company.save()
    return company


def create_b2b_companies(*, quantity: int) -> list[dict[str, Any]]:
    if quantity <= 0:
        raise WebmaniaB2BServiceError("A quantidade de empresas deve ser maior que zero.")

    url = _build_companies_url()

    try:
        response = requests.post(url, json={"quantidade": quantity}, headers=_build_headers(), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = _request_exception_message(exc, default="Falha ao criar empresas na Webmania")
        raise WebmaniaB2BServiceError(message) from exc

    data = _parse_json_response(response, error_message="Resposta inválida da API de criação de empresas.")
    if isinstance(data, dict):
        error_message = _extract_error_message(data)
        if error_message:
            raise WebmaniaB2BServiceError(error_message)
    if not isinstance(data, list):
        raise WebmaniaB2BServiceError("Resposta inválida da API ao criar empresas.")

    companies = [item for item in data if isinstance(item, dict)]
    if not companies:
        raise WebmaniaB2BServiceError("A API da Webmania não retornou as credenciais da nova empresa.")
    return companies


def list_b2b_companies() -> list[dict[str, Any]]:
    url = _build_companies_url()

    try:
        response = requests.get(url, headers=_build_headers(), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = _request_exception_message(exc, default="Falha ao listar empresas na Webmania")
        raise WebmaniaB2BServiceError(message) from exc

    data = _parse_json_response(response, error_message="Resposta inválida da API de listagem de empresas.")
    if isinstance(data, dict):
        error_message = _extract_error_message(data)
        if error_message:
            raise WebmaniaB2BServiceError(error_message)
    if not isinstance(data, list):
        raise WebmaniaB2BServiceError("Resposta inválida da API ao listar empresas.")

    return [item for item in data if isinstance(item, dict)]


def sync_b2b_companies_to_database() -> list[WebmaniaCompany]:
    companies_payload = list_b2b_companies()
    synced_companies: list[WebmaniaCompany] = []
    for payload in companies_payload:
        company = _upsert_company_from_payload(payload=payload)
        if company is not None:
            synced_companies.append(company)
    return synced_companies


def list_local_b2b_companies() -> list[WebmaniaCompany]:
    queryset = WebmaniaCompany.objects.exclude(webmania_company_id="").order_by("razao_social", "nome_completo", "webmania_company_id")
    return list(queryset)


def get_b2b_requests(*, month: int | None = None, year: int | None = None) -> dict[str, Any]:
    query_params: dict[str, str] = {}
    if month is not None:
        query_params["mes"] = f"{month:02d}"
    if year is not None:
        query_params["ano"] = str(year)

    try:
        response = requests.get(_build_requests_url(), params=query_params, headers=_build_headers(), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = _request_exception_message(exc, default="Falha ao consultar requisições na Webmania")
        raise WebmaniaB2BServiceError(message) from exc

    data = _parse_json_response(response, error_message="Resposta inválida da API de requisições.")
    if not isinstance(data, dict):
        raise WebmaniaB2BServiceError("Resposta inválida da API ao consultar requisições.")

    error_message = _extract_error_message(data)
    if error_message:
        raise WebmaniaB2BServiceError(error_message)

    return data


def provision_webmania_company_for_workshop(*, workshop: Workshop) -> WebmaniaCompany:
    companies = create_b2b_companies(quantity=1)
    company_payload = companies[0]
    company = _upsert_company_from_payload(payload=company_payload, workshop=workshop)
    if company is None:
        raise WebmaniaB2BServiceError("Não foi possível vincular a empresa criada na Webmania à oficina.")

    if not company.cnpj:
        company.cnpj = _clean_string(workshop.cnpj)
    if not company.razao_social:
        company.razao_social = _clean_string(workshop.name)
    if not company.telefone:
        company.telefone = _clean_string(workshop.phone)
    if not company.endereco:
        company.endereco = _clean_string(workshop.address)
    if not company.uf:
        company.uf = _clean_string(workshop.uf)
    company.save(update_fields=["cnpj", "razao_social", "telefone", "endereco", "uf"])

    return company


def update_webmania_company(*, company: WebmaniaCompany, payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        raise WebmaniaB2BServiceError("Informe ao menos um campo para atualizar a empresa.")

    try:
        response = requests.post(_build_nfe_company_url(), json=payload, headers=_build_company_headers(company), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = _request_exception_message(exc, default="Falha ao atualizar empresa na Webmania")
        raise WebmaniaB2BServiceError(message) from exc

    data = _parse_json_response(response, error_message="Resposta inválida da API de atualização da empresa.")
    if not isinstance(data, dict):
        raise WebmaniaB2BServiceError("Resposta inválida da API ao atualizar empresa.")

    error_message = _extract_error_message(data)
    if error_message:
        raise WebmaniaB2BServiceError(error_message)

    return data
