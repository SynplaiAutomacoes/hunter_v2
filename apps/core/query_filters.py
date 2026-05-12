from __future__ import annotations

from datetime import date
from dataclasses import dataclass
from typing import Any, Callable, Literal, Sequence

from django.db.models import QuerySet
from django.http import QueryDict

from apps.core.search import build_accent_insensitive_lookup

FilterKind = Literal["choice", "boolean", "icontains", "iexact", "date_gte", "date_lte"]
ValueNormalizer = Callable[[str], str]


@dataclass(frozen=True)
class QueryParamFilter:
    param_name: str
    lookup: str
    kind: FilterKind
    allowed_values: frozenset[str] = frozenset()
    normalizer: ValueNormalizer | None = None


def _normalize_param_values(params: QueryDict, *, filter_config: QueryParamFilter) -> list[str]:
    normalized_values: list[str] = []
    for raw_value in params.getlist(filter_config.param_name):
        value = str(raw_value or "").strip()
        if not value:
            continue

        if filter_config.normalizer is not None:
            value = filter_config.normalizer(value).strip()

        if value:
            normalized_values.append(value)

    return normalized_values


def _normalize_param_value(params: QueryDict, *, filter_config: QueryParamFilter) -> str:
    raw_value = str(params.get(filter_config.param_name) or "").strip()
    if not raw_value:
        return ""

    if filter_config.normalizer is None:
        return raw_value

    return filter_config.normalizer(raw_value).strip()


def _parse_date_param(raw_value: str) -> date | None:
    try:
        return date.fromisoformat(raw_value)
    except ValueError:
        return None


def apply_query_param_filters(
    queryset: QuerySet[Any],
    *,
    params: QueryDict,
    filter_configs: Sequence[QueryParamFilter],
) -> QuerySet[Any]:
    filtered_queryset = queryset

    for filter_config in filter_configs:
        if filter_config.kind == "choice":
            raw_values = _normalize_param_values(params, filter_config=filter_config)
            if not raw_values:
                continue

            valid_values = [raw_value for raw_value in dict.fromkeys(raw_values) if raw_value in filter_config.allowed_values]
            if not valid_values:
                continue

            if len(valid_values) == 1:
                filtered_queryset = filtered_queryset.filter(**{filter_config.lookup: valid_values[0]})
            else:
                filtered_queryset = filtered_queryset.filter(**{f"{filter_config.lookup}__in": valid_values})
            continue

        raw_value = _normalize_param_value(params, filter_config=filter_config)
        if not raw_value:
            continue

        if filter_config.kind == "boolean":
            if raw_value not in {"0", "1"}:
                continue
            filtered_queryset = filtered_queryset.filter(**{filter_config.lookup: raw_value == "1"})
            continue

        if filter_config.kind == "icontains":
            filtered_queryset = filtered_queryset.filter(**{build_accent_insensitive_lookup(filter_config.lookup): raw_value})
            continue

        if filter_config.kind == "date_gte":
            parsed_date = _parse_date_param(raw_value)
            if parsed_date is None:
                continue
            filtered_queryset = filtered_queryset.filter(**{f"{filter_config.lookup}__gte": parsed_date})
            continue

        if filter_config.kind == "date_lte":
            parsed_date = _parse_date_param(raw_value)
            if parsed_date is None:
                continue
            filtered_queryset = filtered_queryset.filter(**{f"{filter_config.lookup}__lte": parsed_date})
            continue

        filtered_queryset = filtered_queryset.filter(**{f"{filter_config.lookup}__iexact": raw_value})

    return filtered_queryset


def apply_is_active_filter(
    queryset: QuerySet[Any],
    *,
    params: QueryDict,
    param_name: str = "is_active",
    lookup: str = "is_active",
) -> QuerySet[Any]:
    raw_value = str(params.get(param_name) or "").strip().lower()

    if raw_value == "all":
        return queryset

    if raw_value == "0":
        return queryset.filter(**{lookup: False})

    return queryset.filter(**{lookup: True})
