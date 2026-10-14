from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any, Mapping

from django.conf import settings

from apps.core.infrastructure.services.webmania.webmania_auth import redact_webmania_headers


logger = logging.getLogger(__name__)

_last_emission_request: ContextVar[dict[str, Any] | None] = ContextVar("webmania_last_emission_request", default=None)


def webmania_emission_request_logs_enabled() -> bool:
    return bool(getattr(settings, "WEBMANIA_EMISSION_REQUEST_LOGS", True))


def _serialize_for_log(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    except TypeError:
        return str(value)


def remember_webmania_emission_request(
    *,
    kind: str,
    action: str,
    url: str,
    payload: Mapping[str, Any] | dict[str, Any],
    headers: Mapping[str, str] | dict[str, str] | None = None,
) -> dict[str, Any]:
    """Store the last outbound Webmania emission request for error-log enrichment."""
    safe_headers = redact_webmania_headers(dict(headers or {}))
    attrs = {
        "webmania_request_kind": kind,
        "webmania_request_action": action,
        "webmania_request_url": url,
        "webmania_request_headers": _serialize_for_log(safe_headers),
        "webmania_request_body": _serialize_for_log(payload),
    }
    _last_emission_request.set(attrs)
    return attrs


def get_webmania_emission_request_log_attrs() -> dict[str, Any]:
    stored = _last_emission_request.get()
    return dict(stored) if stored else {}


def emission_failure_log_extra(exc: BaseException | None = None, **extra: Any) -> dict[str, Any]:
    """Merge last Webmania request attrs + exception.log_extra + caller extras for logger.exception."""
    attrs = get_webmania_emission_request_log_attrs()
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        log_extra = getattr(current, "log_extra", None)
        if isinstance(log_extra, dict):
            attrs.update({key: value for key, value in log_extra.items() if value is not None})
        current = current.__cause__ or current.__context__
    attrs.update({key: value for key, value in extra.items() if value is not None})
    return attrs


def _request_log_message_parts(attrs: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(attrs.get("webmania_request_url") or ""),
        str(attrs.get("webmania_request_headers") or ""),
        str(attrs.get("webmania_request_body") or ""),
    )


def log_webmania_emission_request(
    *,
    kind: str,
    action: str,
    url: str,
    payload: Mapping[str, Any] | dict[str, Any],
    headers: Mapping[str, str] | dict[str, str] | None = None,
    **extra: Any,
) -> None:
    """
    Remember + ERROR-log the outbound Webmania JSON (same shape as failure logs).
    Headers are redacted. Disable with WEBMANIA_EMISSION_REQUEST_LOGS=0.
    """
    attrs = remember_webmania_emission_request(
        kind=kind,
        action=action,
        url=url,
        payload=payload,
        headers=headers,
    )
    if not webmania_emission_request_logs_enabled():
        return

    request_url, request_headers, request_body = _request_log_message_parts(attrs)
    extras = {key: value for key, value in extra.items() if value is not None}
    # ERROR (not INFO): same visibility as failure logs in Grafana/aggregators that filter by level.
    logger.error(
        "webmania_emission_request kind=%s action=%s request_url=%s request_headers=%s request_body=%s",
        kind,
        action,
        request_url,
        request_headers,
        request_body,
        extra={**attrs, **extras},
    )


def log_webmania_emission_failure(*, kind: str, action: str, reason: str, **extra: Any) -> None:
    """Always ERROR-log with the request body/headers that caused the failure (any error type)."""
    attrs = emission_failure_log_extra(**extra)
    request_url, request_headers, request_body = _request_log_message_parts(attrs)
    logger.error(
        "webmania_emission_failed kind=%s action=%s reason=%s request_url=%s request_headers=%s request_body=%s",
        kind,
        action,
        reason,
        request_url,
        request_headers,
        request_body,
        extra={
            "webmania_kind": kind,
            "webmania_action": action,
            "webmania_failure_reason": reason,
            **attrs,
        },
    )


def log_emission_view_failure(logger_: logging.Logger, message: str, exc: BaseException, **extra: Any) -> None:
    """View-layer exception log with request_url/headers/body always in the message text."""
    attrs = emission_failure_log_extra(exc, **extra)
    request_url, request_headers, request_body = _request_log_message_parts(attrs)
    logger_.exception(
        "%s request_url=%s request_headers=%s request_body=%s",
        message,
        request_url,
        request_headers,
        request_body,
        extra=attrs,
    )
