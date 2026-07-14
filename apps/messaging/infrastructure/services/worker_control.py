from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class MessageWorkerControlError(Exception):
    pass


def stop_workshop_dispatch(*, workshop_id: int) -> bool:
    """POST {MESSAGE_WORKER_BASE_URL}/stop with cancelled status for a workshop.

    Returns True when the request was attempted and succeeded.
    Returns False when the base URL is not configured (graceful skip).
    """
    base_url = str(getattr(settings, "MESSAGE_WORKER_BASE_URL", "") or "").strip().rstrip("/")
    if not base_url:
        logger.warning(
            "message_worker_stop_skipped_missing_base_url",
            extra={"workshop_id": workshop_id},
        )
        return False

    url = f"{base_url}/stop"
    payload: dict[str, Any] = {"status": "cancelled", "workshop_id": workshop_id}

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception(
            "message_worker_stop_failed",
            extra={"workshop_id": workshop_id, "url": url},
        )
        raise MessageWorkerControlError(f"Falha ao cancelar envio no worker: {exc}") from exc

    logger.info(
        "message_worker_stop_ok",
        extra={"workshop_id": workshop_id, "url": url, "status_code": response.status_code},
    )
    return True
