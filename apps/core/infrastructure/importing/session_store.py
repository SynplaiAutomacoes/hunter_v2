from __future__ import annotations

import uuid
from typing import Any

from django.core.cache import cache

from apps.core.infrastructure.importing.schema import ParsedSpreadsheet

IMPORT_CACHE_TTL_SECONDS = 60 * 60
IMPORT_CACHE_PREFIX = "data_import:"


def _cache_key(token: str) -> str:
    return f"{IMPORT_CACHE_PREFIX}{token}"


def create_import_session(
    *,
    entity_key: str,
    workshop_id: int,
    user_id: int,
    spreadsheet: ParsedSpreadsheet,
    options: dict[str, Any] | None = None,
) -> str:
    token = uuid.uuid4().hex
    payload = {
        "entity_key": entity_key,
        "workshop_id": workshop_id,
        "user_id": user_id,
        "filename": spreadsheet.filename,
        "source_format": spreadsheet.source_format,
        "headers": spreadsheet.headers,
        "rows": spreadsheet.rows,
        "options": options or {},
        "mapping": {},
    }
    cache.set(_cache_key(token), payload, timeout=IMPORT_CACHE_TTL_SECONDS)
    return token


def get_import_session(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    payload = cache.get(_cache_key(token))
    return payload if isinstance(payload, dict) else None


def update_import_session(token: str, **updates: Any) -> dict[str, Any] | None:
    payload = get_import_session(token)
    if payload is None:
        return None
    payload.update(updates)
    cache.set(_cache_key(token), payload, timeout=IMPORT_CACHE_TTL_SECONDS)
    return payload


def delete_import_session(token: str) -> None:
    if token:
        cache.delete(_cache_key(token))


def spreadsheet_from_session(payload: dict[str, Any]) -> ParsedSpreadsheet:
    return ParsedSpreadsheet(
        headers=list(payload.get("headers") or []),
        rows=list(payload.get("rows") or []),
        filename=str(payload.get("filename") or ""),
        source_format=str(payload.get("source_format") or ""),
    )
