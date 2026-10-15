from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FieldType(str, Enum):
    STRING = "string"
    TEXT = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    MONEY = "money"
    DATE = "date"
    BOOLEAN = "boolean"
    DOCUMENT = "document"
    PHONE = "phone"
    EMAIL = "email"
    DURATION = "duration"
    CHOICE = "choice"


@dataclass(slots=True, frozen=True)
class ImportField:
    key: str
    label: str
    required: bool = False
    field_type: FieldType = FieldType.STRING
    help_text: str = ""
    choices: tuple[tuple[str, str], ...] = ()


@dataclass(slots=True, frozen=True)
class ImportEntitySchema:
    entity_key: str
    label: str
    fields: tuple[ImportField, ...]
    description: str = ""
    example_headers: tuple[str, ...] = ()
    example_rows: tuple[tuple[str, ...], ...] = ()
    example_notes: str = ""

    def field_by_key(self, key: str) -> ImportField | None:
        for import_field in self.fields:
            if import_field.key == key:
                return import_field
        return None

    def required_keys(self) -> tuple[str, ...]:
        return tuple(f.key for f in self.fields if f.required)


class ImportRowError(Exception):
    """Raised when a single import row cannot be created."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(slots=True)
class ImportRowResult:
    row_number: int
    success: bool
    message: str = ""
    created_id: int | None = None


@dataclass(slots=True)
class ImportBatchResult:
    success_count: int = 0
    error_count: int = 0
    results: list[ImportRowResult] = field(default_factory=list)

    def add(self, result: ImportRowResult) -> None:
        self.results.append(result)
        if result.success:
            self.success_count += 1
        else:
            self.error_count += 1


@dataclass(slots=True)
class ParsedSpreadsheet:
    headers: list[str]
    rows: list[dict[str, Any]]
    filename: str
    source_format: str
