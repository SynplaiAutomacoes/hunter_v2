from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractBaseUser

from apps.core.infrastructure.importing.base import ImportAdapter
from apps.core.infrastructure.importing.mapper import apply_mapping
from apps.core.infrastructure.importing.schema import ImportBatchResult, ImportRowError, ImportRowResult, ParsedSpreadsheet
from apps.workshops.models.workshops import Workshop


def prepare_mapped_rows(
    spreadsheet: ParsedSpreadsheet,
    *,
    mapping: dict[str, str],
    schema,
) -> tuple[list[tuple[int, dict[str, Any]]], list[ImportRowResult]]:
    """Return successfully mapped rows and mapping-time errors."""
    mapped_rows: list[tuple[int, dict[str, Any]]] = []
    errors: list[ImportRowResult] = []
    for index, row in enumerate(spreadsheet.rows, start=2):  # header is row 1
        try:
            mapped = apply_mapping(row, mapping=mapping, schema=schema)
            mapped_rows.append((index, mapped))
        except ImportRowError as exc:
            errors.append(ImportRowResult(row_number=index, success=False, message=exc.message))
    return mapped_rows, errors


def run_import(
    *,
    adapter: ImportAdapter,
    workshop: Workshop,
    spreadsheet: ParsedSpreadsheet,
    mapping: dict[str, str],
    user: AbstractBaseUser | None = None,
    options: dict[str, Any] | None = None,
) -> ImportBatchResult:
    schema = adapter.get_schema(workshop, options=options)
    mapped_rows, mapping_errors = prepare_mapped_rows(spreadsheet, mapping=mapping, schema=schema)
    batch = adapter.import_rows(workshop, mapped_rows, user=user, options=options)
    for error in mapping_errors:
        batch.add(error)
    return batch
