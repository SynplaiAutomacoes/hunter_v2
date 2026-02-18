from __future__ import annotations

from django.conf import settings

from apps.finance.models import WebmaniaCompany
from apps.finance.services.webmania_secrets import decrypt_secret


class WebmaniaAuthError(Exception):
    pass


_SENSITIVE_HEADER_KEYS = {
    "Authorization",
    "X-Consumer-Key",
    "X-Consumer-Secret",
    "X-Access-Token",
    "X-Access-Token-Secret",
}


def _mask_value(raw_value: str) -> str:
    value = _sanitize_value(raw_value)
    if not value:
        return ""
    if len(value) <= 6:
        return "***"
    return f"{value[:4]}...{value[-2:]}"


def _sanitize_value(raw_value: object) -> str:
    value = str(raw_value or "").strip()
    while len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return value


def sanitize_webmania_setting(raw_value: object) -> str:
    return _sanitize_value(raw_value)


def should_use_global_webmania_auth() -> bool:
    ambient_value = _sanitize_value(getattr(settings, "WEBMANIA_AMBIENT", "2")) or "2"
    return ambient_value == "2"


def redact_webmania_headers(headers: dict[str, str]) -> dict[str, str]:
    safe_headers = dict(headers)
    for key in _SENSITIVE_HEADER_KEYS:
        if key in safe_headers:
            if key == "Authorization" and safe_headers[key].startswith("Bearer "):
                bearer_token = safe_headers[key].removeprefix("Bearer ")
                safe_headers[key] = f"Bearer {_mask_value(bearer_token)}"
                continue
            safe_headers[key] = _mask_value(safe_headers[key])
    return safe_headers


def _build_headers_from_credentials(*, consumer_key: str, consumer_secret: str, access_token: str, access_token_secret: str, api_key: str = "") -> dict[str, str]:
    normalized_consumer_key = _sanitize_value(consumer_key)
    normalized_consumer_secret = _sanitize_value(consumer_secret)
    normalized_access_token = _sanitize_value(access_token)
    normalized_access_token_secret = _sanitize_value(access_token_secret)

    missing_fields: list[str] = []
    if not normalized_consumer_key:
        missing_fields.append("X-Consumer-Key")
    if not normalized_consumer_secret:
        missing_fields.append("X-Consumer-Secret")
    if not normalized_access_token:
        missing_fields.append("X-Access-Token")
    if not normalized_access_token_secret:
        missing_fields.append("X-Access-Token-Secret")

    if missing_fields:
        missing = ", ".join(missing_fields)
        raise WebmaniaAuthError(f"Credenciais Webmania incompletas: {missing}.")

    headers = {
        "Content-Type": "application/json",
        "X-Consumer-Key": normalized_consumer_key,
        "X-Consumer-Secret": normalized_consumer_secret,
        "X-Access-Token": normalized_access_token,
        "X-Access-Token-Secret": normalized_access_token_secret,
    }

    normalized_api_key = _sanitize_value(api_key)
    if normalized_api_key:
        headers["Authorization"] = f"Bearer {normalized_api_key}"

    return headers


def build_webmania_headers_for_company(company: WebmaniaCompany) -> dict[str, str]:
    return _build_headers_from_credentials(
        consumer_key=decrypt_secret(company.consumer_key),
        consumer_secret=decrypt_secret(company.consumer_secret),
        access_token=decrypt_secret(company.access_token),
        access_token_secret=decrypt_secret(company.access_token_secret),
        api_key=decrypt_secret(company.bearer_access_token),
    )


def build_webmania_headers(*, workshop=None) -> dict[str, str]:
    if workshop is not None:
        company = WebmaniaCompany.objects.filter(workshop=workshop).first()
        if company is None:
            raise WebmaniaAuthError("A oficina ativa não possui empresa Webmania vinculada.")

        return build_webmania_headers_for_company(company)

    consumer_key = _sanitize_value(getattr(settings, "WEBMANIA_CONSUMER_KEY", ""))
    consumer_secret = _sanitize_value(getattr(settings, "WEBMANIA_CONSUMER_SECRET", ""))
    access_token = _sanitize_value(getattr(settings, "WEBMANIA_ACCESS_TOKEN", ""))
    access_token_secret = _sanitize_value(getattr(settings, "WEBMANIA_ACCESS_TOKEN_SECRET", ""))

    missing_fields: list[str] = []
    if not consumer_key:
        missing_fields.append("WEBMANIA_CONSUMER_KEY")
    if not consumer_secret:
        missing_fields.append("WEBMANIA_CONSUMER_SECRET")
    if not access_token:
        missing_fields.append("WEBMANIA_ACCESS_TOKEN")
    if not access_token_secret:
        missing_fields.append("WEBMANIA_ACCESS_TOKEN_SECRET")

    if missing_fields:
        missing = ", ".join(missing_fields)
        raise WebmaniaAuthError(f"Configure as credenciais da Webmania no ambiente: {missing}.")

    api_key = _sanitize_value(getattr(settings, "WEBMANIA_API_KEY", ""))
    return _build_headers_from_credentials(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        api_key=api_key,
    )


def build_webmania_b2b_headers() -> dict[str, str]:
    consumer_key = _sanitize_value(getattr(settings, "WEBMANIA_B2B_CONSUMER_KEY", "")) or _sanitize_value(getattr(settings, "WEBMANIA_CONSUMER_KEY", ""))
    consumer_secret = _sanitize_value(getattr(settings, "WEBMANIA_B2B_CONSUMER_SECRET", "")) or _sanitize_value(getattr(settings, "WEBMANIA_CONSUMER_SECRET", ""))
    access_token = _sanitize_value(getattr(settings, "WEBMANIA_B2B_ACCESS_TOKEN", "")) or _sanitize_value(getattr(settings, "WEBMANIA_ACCESS_TOKEN", ""))
    access_token_secret = _sanitize_value(getattr(settings, "WEBMANIA_B2B_ACCESS_TOKEN_SECRET", "")) or _sanitize_value(getattr(settings, "WEBMANIA_ACCESS_TOKEN_SECRET", ""))

    return _build_headers_from_credentials(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
    )
