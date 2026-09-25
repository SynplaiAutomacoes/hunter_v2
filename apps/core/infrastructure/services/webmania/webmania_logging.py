from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from django.conf import settings


logger = logging.getLogger(__name__)


def webmania_emission_request_logs_enabled() -> bool:
    return bool(getattr(settings, "WEBMANIA_EMISSION_REQUEST_LOGS", True))


def log_webmania_emission_request(
    *,
    kind: str,
    action: str,
    url: str,
    payload: Mapping[str, Any] | dict[str, Any],
    **extra: Any,
) -> None:
    """
    Log the full JSON body sent to Webmania on fiscal emission / preview.
    Headers are intentionally omitted (contain credentials).
    """
    if not webmania_emission_request_logs_enabled():
        return

    try:
        body = json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)
    except TypeError:
        body = str(payload)

    extras = {key: value for key, value in extra.items() if value is not None}
    logger.info(
        "webmania_emission_request kind=%s action=%s url=%s payload=%s",
        kind,
        action,
        url,
        body,
        extra={"webmania_kind": kind, "webmania_action": action, "webmania_url": url, **extras},
    )
