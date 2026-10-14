from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.core.infrastructure.importing.schema import FieldType, ImportEntitySchema, ImportField, ImportRowError


def normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", ascii_text.lower())


def suggest_mapping(headers: list[str], schema: ImportEntitySchema) -> dict[str, str]:
    """Map system field key -> source header name (best effort)."""
    header_by_norm = {normalize_label(h): h for h in headers}
    mapping: dict[str, str] = {}
    for import_field in schema.fields:
        candidates = [import_field.key, import_field.label, *(_choice_labels(import_field))]
        for candidate in candidates:
            match = header_by_norm.get(normalize_label(candidate))
            if match:
                mapping[import_field.key] = match
                break
    return mapping


def _choice_labels(import_field: ImportField) -> list[str]:
    return [label for _, label in import_field.choices]


def parse_boolean(raw: str) -> bool | None:
    value = normalize_label(raw)
    if not value:
        return None
    if value in {"1", "true", "sim", "s", "yes", "y", "ativo", "verdadeiro"}:
        return True
    if value in {"0", "false", "nao", "n", "no", "inativo", "falso"}:
        return False
    raise ImportRowError(f"Valor booleano inválido: '{raw}'.")


def parse_decimal(raw: str) -> Decimal | None:
    text = (raw or "").strip()
    if not text:
        return None
    cleaned = text.replace("R$", "").replace(" ", "").strip()
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ImportRowError(f"Número inválido: '{raw}'.") from exc


def parse_integer(raw: str) -> int | None:
    decimal_value = parse_decimal(raw)
    if decimal_value is None:
        return None
    if decimal_value != decimal_value.to_integral_value():
        raise ImportRowError(f"Número inteiro inválido: '{raw}'.")
    return int(decimal_value)


def parse_date(raw: str) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    # Excel serial as string
    try:
        serial = Decimal(text)
        if serial > 0:
            return (datetime(1899, 12, 30) + timedelta(days=float(serial))).date()
    except (InvalidOperation, OverflowError, ValueError):
        pass
    raise ImportRowError(f"Data inválida: '{raw}'. Use DD/MM/AAAA.")


def parse_duration(raw: str) -> timedelta | None:
    text = (raw or "").strip().lower()
    if not text:
        return None

    hour_match = re.match(r"^(\d+)\s*h(?:oras?)?\s*(?:(\d+)\s*m(?:in(?:utos?)?)?)?$", text)
    if hour_match:
        hours = int(hour_match.group(1))
        minutes = int(hour_match.group(2) or 0)
        return timedelta(hours=hours, minutes=minutes)

    if re.match(r"^\d+:\d{1,2}$", text):
        hours_str, minutes_str = text.split(":")
        return timedelta(hours=int(hours_str), minutes=int(minutes_str))

    if text.isdigit():
        return timedelta(minutes=int(text))

    raise ImportRowError(f"Duração inválida: '{raw}'. Use HH:MM, minutos ou 1h30m.")


def parse_document(raw: str) -> str | None:
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    return digits or None


def coerce_value(raw: object, import_field: ImportField) -> Any:
    text = "" if raw is None else str(raw).strip()
    field_type = import_field.field_type

    if not text:
        # Campos ignorados/vazios ficam vazios; dinheiro/número usam zero genérico.
        if field_type == FieldType.MONEY:
            return Decimal("0")
        if field_type == FieldType.INTEGER:
            return 0
        if field_type == FieldType.DECIMAL:
            return Decimal("0")
        return None

    if field_type in {FieldType.STRING, FieldType.TEXT, FieldType.EMAIL, FieldType.PHONE}:
        return text
    if field_type == FieldType.DOCUMENT:
        return parse_document(text)
    if field_type == FieldType.INTEGER:
        try:
            return parse_integer(text)
        except ImportRowError:
            return 0
    if field_type in {FieldType.DECIMAL, FieldType.MONEY}:
        try:
            parsed = parse_decimal(text)
        except ImportRowError:
            return Decimal("0")
        return parsed if parsed is not None else Decimal("0")
    if field_type == FieldType.DATE:
        return parse_date(text)
    if field_type == FieldType.BOOLEAN:
        return parse_boolean(text)
    if field_type == FieldType.DURATION:
        return parse_duration(text)
    if field_type == FieldType.CHOICE:
        return _coerce_choice(text, import_field)
    return text


def _coerce_choice(text: str, import_field: ImportField) -> str:
    normalized = normalize_label(text)
    for value, label in import_field.choices:
        if normalize_label(value) == normalized or normalize_label(label) == normalized:
            return value
    # Valor inválido: deixa vazio para o adapter aplicar default (ex.: unidade UND).
    return ""


def apply_mapping(
    row: dict[str, Any],
    *,
    mapping: dict[str, str],
    schema: ImportEntitySchema,
) -> dict[str, Any]:
    """Build mapped dict keyed by system field from a source row and column mapping.

    Campos marcados como "Ignorar" ficam de fora (vazios); adapters aplicam defaults
    quando o modelo exige valor (grupo genérico, R$ 0,00, etc.).
    """
    mapped: dict[str, Any] = {}
    for import_field in schema.fields:
        source_header = mapping.get(import_field.key) or ""
        if not source_header:
            continue
        raw = row.get(source_header, "")
        value = coerce_value(raw, import_field)
        if value is not None and value != "":
            mapped[import_field.key] = value
    return mapped
