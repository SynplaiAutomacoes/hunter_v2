from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Sequence

from django.db.models import QuerySet
from django.http import QueryDict

FilterKind = Literal["choice", "boolean", "icontains", "iexact"]
ValueNormalizer = Callable[[str], str]


@dataclass(frozen=True)
class QueryParamFilter:
    param_name: str
    lookup: str
    kind: FilterKind
    allowed_values: frozenset[str] = frozenset()
    normalizer: ValueNormalizer | None = None


def _normalize_param_value(params: QueryDict, *, filter_config: QueryParamFilter) -> str:
    raw_value = str(params.get(filter_config.param_name) or "").strip()
    if not raw_value:
        return ""

    if filter_config.normalizer is None:
        return raw_value

    return filter_config.normalizer(raw_value).strip()


def apply_query_param_filters(
    queryset: QuerySet[Any],
    *,
    params: QueryDict,
    filter_configs: Sequence[QueryParamFilter],
) -> QuerySet[Any]:
    filtered_queryset = queryset

    for filter_config in filter_configs:
        raw_value = _normalize_param_value(params, filter_config=filter_config)
        if not raw_value:
            continue

        if filter_config.kind == "choice":
            if raw_value not in filter_config.allowed_values:
                continue
            filtered_queryset = filtered_queryset.filter(**{filter_config.lookup: raw_value})
            continue

        if filter_config.kind == "boolean":
            if raw_value not in {"0", "1"}:
                continue
            filtered_queryset = filtered_queryset.filter(**{filter_config.lookup: raw_value == "1"})
            continue

        if filter_config.kind == "icontains":
            filtered_queryset = filtered_queryset.filter(**{f"{filter_config.lookup}__icontains": raw_value})
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
