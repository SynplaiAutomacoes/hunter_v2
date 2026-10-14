from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.infrastructure.importing.schema import ParsedSpreadsheet
from apps.core.infrastructure.models.data_import import DataImportDraft

IMPORT_CACHE_TTL_SECONDS = 60 * 60


def create_import_session(
    *,
    entity_key: str,
    workshop_id: int,
    user_id: int,
    spreadsheet: ParsedSpreadsheet,
    options: dict[str, Any] | None = None,
) -> str:
    token = uuid.uuid4().hex
    now = timezone.now()
    with transaction.atomic():
        DataImportDraft.objects.filter(expires_at__lt=now).delete()
        DataImportDraft.objects.create(
            token=token,
            workshop_id=workshop_id,
            user_id=user_id,
            entity_key=entity_key,
            filename=spreadsheet.filename,
            source_format=spreadsheet.source_format,
            headers=list(spreadsheet.headers),
            rows=list(spreadsheet.rows),
            options=options or {},
            mapping={},
            expires_at=now + timedelta(seconds=IMPORT_CACHE_TTL_SECONDS),
        )
    return token


def get_import_session(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    draft = DataImportDraft.objects.filter(token=token).first()
    if draft is None:
        return None
    if draft.expires_at < timezone.now():
        draft.delete()
        return None
    return _draft_to_payload(draft)


def update_import_session(token: str, **updates: Any) -> dict[str, Any] | None:
    draft = DataImportDraft.objects.filter(token=token).first()
    if draft is None:
        return None
    if draft.expires_at < timezone.now():
        draft.delete()
        return None

    allowed = {"mapping", "options", "headers", "rows", "filename", "source_format"}
    update_fields = ["atualizado_em", "expires_at"]
    for key, value in updates.items():
        if key not in allowed:
            continue
        setattr(draft, key, value)
        update_fields.append(key)

    draft.expires_at = timezone.now() + timedelta(seconds=IMPORT_CACHE_TTL_SECONDS)
    draft.save(update_fields=update_fields)
    return _draft_to_payload(draft)


def delete_import_session(token: str) -> None:
    if token:
        DataImportDraft.objects.filter(token=token).delete()


def spreadsheet_from_session(payload: dict[str, Any]) -> ParsedSpreadsheet:
    return ParsedSpreadsheet(
        headers=list(payload.get("headers") or []),
        rows=list(payload.get("rows") or []),
        filename=str(payload.get("filename") or ""),
        source_format=str(payload.get("source_format") or ""),
    )


def _draft_to_payload(draft: DataImportDraft) -> dict[str, Any]:
    return {
        "entity_key": draft.entity_key,
        "workshop_id": draft.workshop_id,
        "user_id": draft.user_id,
        "filename": draft.filename,
        "source_format": draft.source_format,
        "headers": list(draft.headers or []),
        "rows": list(draft.rows or []),
        "options": dict(draft.options or {}),
        "mapping": dict(draft.mapping or {}),
    }
