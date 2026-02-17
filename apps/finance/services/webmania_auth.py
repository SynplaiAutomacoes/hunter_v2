from __future__ import annotations

from django.conf import settings


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


def build_webmania_headers() -> dict[str, str]:
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

    headers = {
        "Content-Type": "application/json",
        "X-Consumer-Key": consumer_key,
        "X-Consumer-Secret": consumer_secret,
        "X-Access-Token": access_token,
        "X-Access-Token-Secret": access_token_secret,
    }

    api_key = _sanitize_value(getattr(settings, "WEBMANIA_API_KEY", ""))
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    return headers
