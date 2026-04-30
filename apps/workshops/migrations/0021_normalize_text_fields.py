from __future__ import annotations

import re

from django.db import migrations, models


PORTUGUESE_PARTICLES = {
    "da",
    "de",
    "do",
    "das",
    "dos",
    "e",
    "em",
    "o",
    "a",
    "os",
    "as",
    "no",
    "na",
    "nos",
    "nas",
    "ao",
    "aos",
}

WORD_REGEX = re.compile(r"\b[\wÀ-ÿ'-]+\b", re.UNICODE)
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
URL_REGEX = re.compile(r"(https?://\S+|www\.\S+)")
UUID_REGEX = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
FILENAME_REGEX = re.compile(r"\b[^/\\]+\.(?:pdf|docx?|xlsx?|jpe?g|png|gif|txt|csv)\b", re.IGNORECASE)
NUMERIC_REGEX = re.compile(r"^[0-9.,\-]+$")
PLATE_REGEX = re.compile(r"^[A-Z]{3}-?\d[A-Z0-9]\d{2}$", re.IGNORECASE)
ALPHANUMERIC_CODE_REGEX = re.compile(r"(?i)^(?=.*[a-z])(?=.*\d)[a-z0-9\-_/]{4,}$")


def _normalize_token(token: str) -> str:
    return token.strip("'\"()[]{}<>.,;:!?\n\r\t").lower()


def _is_excluded_token(token: str) -> bool:
    if not token:
        return False
    normalized = _normalize_token(token)
    if not normalized:
        return False

    if EMAIL_REGEX.search(normalized):
        return True
    if URL_REGEX.search(normalized):
        return True
    if UUID_REGEX.search(normalized):
        return True
    if FILENAME_REGEX.search(normalized):
        return True
    if NUMERIC_REGEX.match(normalized):
        return True
    if PLATE_REGEX.match(normalized.upper()):
        return True
    if ALPHANUMERIC_CODE_REGEX.match(normalized):
        return True

    return False


def _capitalize_word(word: str) -> str:
    if not word:
        return word
    lower = word.lower()
    for index, char in enumerate(lower):
        if char.isalpha():
            return lower[:index] + char.upper() + lower[index + 1 :]
    return lower


def _title_case_word(word: str) -> str:
    if not word:
        return word
    parts = re.split(r"([\-'])", word)
    out: list[str] = []
    for part in parts:
        if part in {"-", "'"}:
            out.append(part)
        else:
            out.append(_capitalize_word(part))
    return "".join(out)


def sentence_case(value: str) -> str:
    if not value or not value.strip():
        return value
    parts = re.split(r"([.!?]+\s*)", value)
    output: list[str] = []

    for idx in range(0, len(parts), 2):
        segment = parts[idx]
        delimiter = parts[idx + 1] if idx + 1 < len(parts) else ""
        tokens = re.split(r"(\b[\wÀ-ÿ'-]+\b)", segment, flags=re.UNICODE)
        first_word = True
        seg_out: list[str] = []
        for token in tokens:
            if not token:
                continue
            if WORD_REGEX.fullmatch(token):
                if _is_excluded_token(token):
                    seg_out.append(token)
                else:
                    if first_word:
                        seg_out.append(_capitalize_word(token))
                        first_word = False
                    else:
                        seg_out.append(token.lower())
            else:
                seg_out.append(token)
        output.append("".join(seg_out))
        output.append(delimiter)

    return "".join(output).strip()


def name_case(value: str) -> str:
    if not value or not value.strip():
        return value

    tokens = re.split(r"(\b[\wÀ-ÿ'-]+\b)", value, flags=re.UNICODE)
    output: list[str] = []
    first_word = True
    for token in tokens:
        if not token:
            continue
        if WORD_REGEX.fullmatch(token):
            if _is_excluded_token(token):
                output.append(token)
                first_word = False
                continue

            normalized = _normalize_token(token)
            if not first_word and normalized in PORTUGUESE_PARTICLES:
                output.append(token.lower())
            else:
                output.append(_title_case_word(token))
            first_word = False
        else:
            output.append(token)
            if any(mark in token for mark in (".", "!", "?")):
                first_word = True

    return "".join(output).strip()


def plate_case(value: str) -> str:
    return (value or "").strip().upper()


NAME_FIELDS = {
    "name",
    "fantasy_name",
    "contact_person",
    "guest_customer_name",
    "razao_social",
    "nome_completo",
    "nome_fantasia",
}

PLATE_FIELDS = {"plate", "guest_vehicle_plate"}

SENTENCE_FIELDS = {
    "title",
    "description",
    "notes",
    "message",
    "reason",
    "observation",
    "problem_description",
    "technical_diagnosis",
    "pdf_observation",
    "cancellation_reason",
    "items_observation",
    "financial_observation",
    "additional_information",
    "service_description",
    "logradouro",
    "complemento",
    "bairro",
    "cidade",
    "endereco",
    "brand",
    "model",
    "color",
    "type",
    "position",
}


EXCLUDED_FIELD_NAME_PARTS = {
    "email",
    "cpf",
    "cnpj",
    "rg",
    "url",
    "token",
    "secret",
    "password",
    "key",
    "uuid",
    "external_id",
    "document_id",
    "content_type",
    "content_name",
    "file",
    "filename",
    "nf",
    "nfe",
    "nfse",
    "access",
    "renavam",
    "chassi",
    "cep",
    "phone",
    "mobile",
}


def _should_exclude_field(field: models.Field) -> bool:
    name = str(getattr(field, "name", "") or "")
    if not name:
        return True
    lowered = name.lower()
    if any(part in lowered for part in EXCLUDED_FIELD_NAME_PARTS):
        return True
    if getattr(field, "choices", None):
        return True
    return False


def _get_unique_constraint_field_sets(model: type[models.Model]) -> list[tuple[str, ...]]:
    unique_field_sets: list[tuple[str, ...]] = []

    for constraint in getattr(model._meta, "constraints", []):
        if isinstance(constraint, models.UniqueConstraint) and constraint.fields:
            unique_field_sets.append(tuple(str(field_name) for field_name in constraint.fields))

    unique_together = getattr(model._meta, "unique_together", ()) or ()
    for field_names in unique_together:
        if isinstance(field_names, str):
            unique_field_sets.append((field_names,))
        else:
            unique_field_sets.append(tuple(str(field_name) for field_name in field_names))

    return unique_field_sets


def _has_unique_conflict(
    model: type[models.Model],
    pk_name: str,
    obj: object,
    normalized_values: dict[str, str],
    unique_field_sets: list[tuple[str, ...]],
    reserved_keys: set[tuple[tuple[str, object], ...]],
) -> bool:
    obj_pk = getattr(obj, pk_name)

    for field_names in unique_field_sets:
        if not any(field_name in normalized_values for field_name in field_names):
            continue

        lookup_items: list[tuple[str, object]] = []
        skip_constraint = False
        for field_name in field_names:
            value = normalized_values.get(field_name, getattr(obj, field_name, None))
            if value is None:
                skip_constraint = True
                break
            lookup_items.append((field_name, value))

        if skip_constraint:
            continue

        lookup_key = tuple(lookup_items)
        if lookup_key in reserved_keys:
            return True

        if model.objects.filter(**dict(lookup_items)).exclude(**{pk_name: obj_pk}).exists():
            return True

    return False


def normalize_text_fields(apps, schema_editor):
    batch_size = 500
    for model in apps.get_models():
        # skip auto-created through models
        if getattr(model._meta, "auto_created", False):
            continue

        string_fields: list[models.Field] = [field for field in model._meta.fields if isinstance(field, (models.CharField, models.TextField)) and not _should_exclude_field(field)]

        if not string_fields:
            continue

        pk_name = model._meta.pk.name
        field_names = [field.name for field in string_fields]
        qs = model.objects.all().only(pk_name, *field_names)
        unique_field_sets = _get_unique_constraint_field_sets(model)
        reserved_keys: set[tuple[tuple[str, object], ...]] = set()

        updates: list[object] = []
        for obj in qs.iterator(chunk_size=batch_size):
            normalized_values: dict[str, str] = {}
            for field in string_fields:
                field_name = field.name
                raw = getattr(obj, field_name, None)
                if raw is None:
                    continue
                if not isinstance(raw, str):
                    continue

                if field_name in PLATE_FIELDS:
                    new_value = plate_case(raw)
                elif field_name in NAME_FIELDS:
                    new_value = name_case(raw)
                elif field_name in SENTENCE_FIELDS:
                    new_value = sentence_case(raw)
                else:
                    # default: only normalize clearly human-readable fields
                    continue

                if new_value != raw:
                    normalized_values[field_name] = new_value

            if not normalized_values:
                continue

            if _has_unique_conflict(model, pk_name, obj, normalized_values, unique_field_sets, reserved_keys):
                continue

            for field_name, new_value in normalized_values.items():
                setattr(obj, field_name, new_value)

            for field_names in unique_field_sets:
                if not any(field_name in normalized_values for field_name in field_names):
                    continue
                key_items: list[tuple[str, object]] = []
                skip_constraint = False
                for field_name in field_names:
                    value = getattr(obj, field_name, None)
                    if value is None:
                        skip_constraint = True
                        break
                    key_items.append((field_name, value))
                if not skip_constraint:
                    reserved_keys.add(tuple(key_items))

            if normalized_values:
                updates.append(obj)

            if len(updates) >= batch_size:
                model.objects.bulk_update(updates, field_names, batch_size=batch_size)
                updates = []

        if updates:
            model.objects.bulk_update(updates, field_names, batch_size=batch_size)


class Migration(migrations.Migration):
    dependencies = [
        ("workshops", "0020_merge_workshop_storage_branches"),
    ]

    operations = [
        migrations.RunPython(normalize_text_fields, migrations.RunPython.noop),
    ]
