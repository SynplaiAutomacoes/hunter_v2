from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.db.models import Q, QuerySet


def build_accent_insensitive_lookup(lookup: str, *, kind: str = "icontains") -> str:
    normalized_lookup = str(lookup or "").strip().replace(".", "__")
    return f"{normalized_lookup}__unaccent__{kind}"


def build_text_search_query(*, search_value: str, lookups: Iterable[str]) -> Q:
    query = Q()
    has_clauses = False

    for raw_lookup in lookups:
        lookup = str(raw_lookup or "").strip().replace(".", "__")
        if not lookup:
            continue

        clause = Q(**{build_accent_insensitive_lookup(lookup): search_value})
        query = clause if not has_clauses else query | clause
        has_clauses = True

    return query


def apply_text_search(queryset: QuerySet[Any], *, search_value: str, lookups: Iterable[str]) -> QuerySet[Any]:
    query = build_text_search_query(search_value=search_value, lookups=lookups)
    if not query.children:
        return queryset
    return queryset.filter(query)
