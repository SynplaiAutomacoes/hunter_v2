from __future__ import annotations

from typing import Any

import requests
from django.conf import settings
from django.utils import timezone

from apps.collaborators.models import WorkshopMember
from apps.finance.models.finance import WebmaniaCompany, WebmaniaCompanyTaxType
from apps.core.infrastructure.services.webmania.webmania_auth import (
    WebmaniaAuthError,
    build_webmania_b2b_headers,
    build_webmania_headers,
    sanitize_webmania_setting,
    should_use_global_webmania_auth,
)
from apps.core.infrastructure.services.webmania.webmania_errors import build_webmania_request_exception_message, extract_webmania_error_message
from apps.core.infrastructure.services.webmania.webmania_secrets import encrypt_secret
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import create_default_monthly_costs


class WebmaniaB2BServiceError(Exception):
    pass


_SENSITIVE_COMPANY_FIELDS = (
    "consumer_key",
    "consumer_secret",
    "access_token",
    "access_token_secret",
    "bearer_access_token",
    "nfse_password",
    "nfse_token",
    "certificado_senha",
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
    return extract_webmania_error_message(payload)


def _request_exception_message(exc: requests.RequestException, *, default: str) -> str:
    return build_webmania_request_exception_message(exc, default=default)


def _parse_json_response(response: requests.Response, *, error_message: str) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise WebmaniaB2BServiceError(error_message) from exc


def _build_headers(*, workshop: Workshop | None = None, force_global: bool = False) -> dict[str, str]:
    try:
        if force_global or should_use_global_webmania_auth():
            return build_webmania_b2b_headers()
        if workshop is None:
            raise WebmaniaB2BServiceError("A oficina ativa é obrigatória para autenticação fora do ambiente 2.")
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise WebmaniaB2BServiceError(str(exc)) from exc


def _build_company_headers(company: WebmaniaCompany) -> dict[str, str]:
    try:
        if should_use_global_webmania_auth():
            return build_webmania_headers()

        workshop = getattr(company, "workshop", None)
        if workshop is None:
            raise WebmaniaB2BServiceError("A empresa precisa estar vinculada a uma oficina para autenticação fora do ambiente 2.")
        return build_webmania_headers(workshop=workshop)
    except WebmaniaAuthError as exc:
        raise WebmaniaB2BServiceError(str(exc)) from exc


def _clean_string(value: object) -> str:
    return str(value or "").strip()


def _only_digits(value: object) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())


def _format_cnpj_for_workshop(value: object) -> str:
    digits = _only_digits(value)
    if len(digits) != 14:
        return ""
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _normalize_workshop_uf(value: object) -> str:
    raw_uf = _clean_string(value).upper()
    if len(raw_uf) == 2 and raw_uf.isalpha():
        return raw_uf
    return "SP"


def _normalize_workshop_phone(value: object) -> str:
    raw_phone = _clean_string(value)
    if raw_phone:
        return raw_phone
    return "+5511999999999"


def _build_workshop_name(payload: dict[str, Any]) -> str:
    return _clean_string(payload.get("razao_social")) or _clean_string(payload.get("nome_fantasia")) or _clean_string(payload.get("nome_completo")) or f"Oficina {(_clean_string(payload.get('id')) or '-')}"


def _build_workshop_address(payload: dict[str, Any]) -> str:
    address = _clean_string(payload.get("endereco"))
    number = _clean_string(payload.get("numero"))
    complement = _clean_string(payload.get("complemento"))

    if not address:
        return "Endereco nao informado"

    parts = [address]
    if number:
        parts.append(number)
    if complement:
        parts.append(complement)
    return ", ".join(parts)


def _ensure_workshop_for_company_payload(*, payload: dict[str, Any], base_workshop: Workshop | None = None, actor_user: Any | None = None) -> Workshop | None:
    account = getattr(base_workshop, "account", None)
    account_id = getattr(base_workshop, "account_id", None)

    if account is None or account_id is None:
        account = getattr(actor_user, "account", None)
        account_id = getattr(actor_user, "account_id", None)

    if account is None or account_id is None:
        return None

    workshop_cnpj = _format_cnpj_for_workshop(payload.get("cnpj"))
    if not workshop_cnpj:
        return None

    workshop = Workshop.objects.filter(cnpj=workshop_cnpj).first()
    if workshop is not None and workshop.account_id != account_id:
        return None

    if workshop is None:
        workshop = Workshop.objects.create(
            account=account,
            name=_build_workshop_name(payload),
            cnpj=workshop_cnpj,
            phone=_normalize_workshop_phone(payload.get("telefone")),
            address=_build_workshop_address(payload),
            uf=_normalize_workshop_uf(payload.get("estado") or payload.get("uf")),
            is_active=True,
        )
        create_default_monthly_costs(workshop=workshop)

    if actor_user is not None:
        director_role = get_or_create_director_role(account=account)
        member, _ = WorkshopMember.objects.get_or_create(
            user=actor_user,
            workshop=workshop,
            defaults={
                "role": director_role,
                "is_active": True,
            },
        )

        update_member_fields: list[str] = []
        if not member.is_active:
            member.is_active = True
            update_member_fields.append("is_active")
        if member.role is None:
            member.role = director_role
            update_member_fields.append("role")
        if update_member_fields:
            member.save(update_fields=update_member_fields)

    return workshop


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


def _extract_sensitive_field_value(*, payload: dict[str, Any], credentials: dict[str, str], field_name: str) -> str:
    credential_value = credentials.get(field_name)
    if credential_value:
        return credential_value
    return _clean_string(payload.get(field_name))


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
        raw_value = _extract_sensitive_field_value(payload=payload, credentials=credentials, field_name=field_name)
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


def create_b2b_companies(*, quantity: int, workshop: Workshop | None = None, force_global: bool = False) -> list[dict[str, Any]]:
    if quantity <= 0:
        raise WebmaniaB2BServiceError("A quantidade de empresas deve ser maior que zero.")

    url = _build_companies_url()

    try:
        response = requests.post(url, json={"quantidade": quantity}, headers=_build_headers(workshop=workshop, force_global=force_global), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = _request_exception_message(exc, default="Falha ao criar empresas")
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
        raise WebmaniaB2BServiceError("A API nao retornou as credenciais da nova empresa.")
    return companies


def list_b2b_companies(*, workshop: Workshop | None = None, force_global_auth: bool = False) -> list[dict[str, Any]]:
    url = _build_companies_url()

    try:
        response = requests.get(url, headers=_build_headers(workshop=workshop, force_global=force_global_auth), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = _request_exception_message(exc, default="Falha ao listar empresas")
        raise WebmaniaB2BServiceError(message) from exc

    data = _parse_json_response(response, error_message="Resposta inválida da API de listagem de empresas.")
    if isinstance(data, dict):
        error_message = _extract_error_message(data)
        if error_message:
            raise WebmaniaB2BServiceError(error_message)
    if not isinstance(data, list):
        raise WebmaniaB2BServiceError("Resposta inválida da API ao listar empresas.")

    return [item for item in data if isinstance(item, dict)]


def sync_b2b_companies_to_database(*, workshop: Workshop | None = None, actor_user: Any | None = None, force_global_auth: bool = False) -> list[WebmaniaCompany]:
    companies_payload = list_b2b_companies(workshop=workshop, force_global_auth=force_global_auth)
    remote_company_ids = {_clean_string(item.get("id")) for item in companies_payload if _clean_string(item.get("id"))}
    account_id = getattr(workshop, "account_id", None)
    if account_id is None:
        account_id = getattr(actor_user, "account_id", None)

    synced_companies: list[WebmaniaCompany] = []
    for payload in companies_payload:
        linked_workshop = _ensure_workshop_for_company_payload(payload=payload, base_workshop=workshop, actor_user=actor_user)

        company = _upsert_company_from_payload(payload=payload, workshop=linked_workshop)
        if company is not None:
            synced_companies.append(company)

    if account_id is not None:
        stale_companies = WebmaniaCompany.objects.filter(workshop__account_id=account_id).exclude(webmania_company_id="")
        if remote_company_ids:
            stale_companies = stale_companies.exclude(webmania_company_id__in=remote_company_ids)
        stale_companies.delete()

    return synced_companies


def list_local_b2b_companies(*, workshop: Workshop | None = None) -> list[WebmaniaCompany]:
    queryset = WebmaniaCompany.objects.exclude(webmania_company_id="")
    account_id = getattr(workshop, "account_id", None)
    if account_id is not None:
        queryset = queryset.filter(workshop__account_id=account_id)

    queryset = queryset.order_by("razao_social", "nome_completo", "webmania_company_id")
    return list(queryset)


def get_b2b_requests(*, month: int | None = None, year: int | None = None, workshop: Workshop | None = None) -> dict[str, Any]:
    query_params: dict[str, str] = {}
    if month is not None:
        query_params["mes"] = f"{month:02d}"
    if year is not None:
        query_params["ano"] = str(year)

    try:
        response = requests.get(_build_requests_url(), params=query_params, headers=_build_headers(workshop=workshop), timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        message = _request_exception_message(exc, default="Falha ao consultar requisicoes")
        raise WebmaniaB2BServiceError(message) from exc

    data = _parse_json_response(response, error_message="Resposta inválida da API de requisições.")
    if not isinstance(data, dict):
        raise WebmaniaB2BServiceError("Resposta inválida da API ao consultar requisições.")

    error_message = _extract_error_message(data)
    if error_message:
        raise WebmaniaB2BServiceError(error_message)

    return data


def provision_webmania_company_for_workshop(*, workshop: Workshop) -> WebmaniaCompany:
    companies = create_b2b_companies(quantity=1, force_global=True)
    company_payload = companies[0]
    company = _upsert_company_from_payload(payload=company_payload, workshop=workshop)
    if company is None:
        raise WebmaniaB2BServiceError("Nao foi possivel vincular a empresa criada à oficina.")

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
        message = _request_exception_message(exc, default="Falha ao atualizar empresa")
        raise WebmaniaB2BServiceError(message) from exc

    data = _parse_json_response(response, error_message="Resposta inválida da API de atualização da empresa.")
    if not isinstance(data, dict):
        raise WebmaniaB2BServiceError("Resposta inválida da API ao atualizar empresa.")

    error_message = _extract_error_message(data)
    if error_message:
        raise WebmaniaB2BServiceError(error_message)

    return data
