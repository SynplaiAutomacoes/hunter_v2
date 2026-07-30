from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.infrastructure.services.webmania.webmania_status import normalize_nfse_batch_status, normalize_nfse_item_status


_ITEM_STATUS_RANK = {
    "processando": 10,
    "contingencia": 20,
    "agendado": 25,
    "aprovado": 30,
    "reprovado": 40,
    "cancelado": 50,
    "substituido": 50,
}

_BATCH_STATUS_RANK = {
    "processando": 10,
    "contingencia": 20,
    "agendado": 25,
    "processado": 30,
    "reprovado": 40,
    "cancelado": 50,
}


def parse_nfse_remote_updated_at(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        parsed = parse_datetime(normalized)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def should_apply_nfse_update(
    *,
    model: str,
    current_status: str,
    current_remote_updated_at: datetime | None,
    payload: dict[str, Any],
) -> bool:
    incoming_remote_updated_at = parse_nfse_remote_updated_at(payload.get("atualizado_em") or payload.get("remote_updated_at"))
    if current_remote_updated_at is not None and incoming_remote_updated_at is not None and incoming_remote_updated_at < current_remote_updated_at:
        return False

    if model == "lote_rps":
        normalized_current = normalize_nfse_batch_status(current_status)
        normalized_incoming = normalize_nfse_batch_status(payload.get("status"))
        ranks = _BATCH_STATUS_RANK
    else:
        normalized_current = normalize_nfse_item_status(current_status)
        normalized_incoming = normalize_nfse_item_status(payload.get("status"))
        ranks = _ITEM_STATUS_RANK

    current_rank = ranks.get(normalized_current, 0)
    incoming_rank = ranks.get(normalized_incoming, 0)
    if current_rank and incoming_rank and incoming_rank < current_rank:
        return False
    return True
