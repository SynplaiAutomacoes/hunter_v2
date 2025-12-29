from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from django.core.exceptions import FieldError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import QuerySet
from django.db.models.expressions import BaseExpression
from django.http import HttpRequest
from django.template import Library
from django.utils.http import urlencode

register = Library()


@dataclass(frozen=True)
class TableColumn:
    label: str
    attr: str | None
    th_class: str = ""
    td_class: str = ""
    sortable: bool = True
    # Opcional: permite customizar o `order_by` quando `sort=<attr>`.
    # Aceita:
    # - str (campo/lookup),
    # - Expression / OrderBy,
    # - sequência de (str|Expression) para ordenar por múltiplos critérios.
    sort_by: str | BaseExpression | Sequence[str | BaseExpression] | None = None


def _resolve_attr(obj: Any, attr: str | None) -> Any:
    if attr in (None, ""):
        return obj

    value: Any = obj
    for part in attr.split("."):
        value = getattr(value, part)
        if callable(value):
            value = value()
    return value


def _normalize_fields(fields: Iterable[Any]) -> list[TableColumn]:
    normalized: list[TableColumn] = []
    for f in fields:
        if isinstance(f, TableColumn):
            normalized.append(f)
            continue

        if isinstance(f, Mapping):
            label = str(f.get("label", ""))
            attr = f.get("attr")
            if attr is not None:
                attr = str(attr)
            normalized.append(
                TableColumn(
                    label=label,
                    attr=attr,
                    th_class=str(f.get("th_class", "")),
                    td_class=str(f.get("td_class", "")),
                    sortable=bool(f.get("sortable", True)),
                    sort_by=f.get("sort_by"),
                )
            )
            continue

        if isinstance(f, (list, tuple)):
            label = str(f[0]) if len(f) > 0 else ""
            attr = str(f[1]) if len(f) > 1 and f[1] is not None else None
            th_class = str(f[2]) if len(f) > 2 else ""
            td_class = str(f[3]) if len(f) > 3 else ""
            sortable = bool(f[4]) if len(f) > 4 else True
            sort_by = f[5] if len(f) > 5 else None
            normalized.append(TableColumn(label=label, attr=attr, th_class=th_class, td_class=td_class, sortable=sortable, sort_by=sort_by))
            continue

        raise TypeError("Cada coluna deve ser um dict, tuple/list ou TableColumn")

    return normalized


def _build_url(request: HttpRequest, *, updates: dict[str, Any]) -> str:
    params = request.GET.copy()
    for key, value in updates.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = str(value)

    qs = urlencode(params, doseq=True)
    return f"{request.path}?{qs}" if qs else request.path


def _as_ordering_terms(col: TableColumn, *, desc: bool) -> list[str | BaseExpression]:
    """Converte a configuração de sort da coluna em uma lista de termos para `order_by`.

    Observação: `sort` (querystring) continua sendo baseado em `col.attr`.
    `col.sort_by` apenas altera como a ordenação é aplicada no QuerySet.
    """

    def _apply_dir(term: str | BaseExpression) -> str | BaseExpression:
        if isinstance(term, str):
            return f"-{term}" if desc else term
        # Expressions suportam `.asc()`/`.desc()` que retornam `OrderBy`.
        return term.desc() if desc else term.asc()

    sort_by = col.sort_by if col.sort_by is not None else col.attr
    if sort_by is None:
        return []

    if isinstance(sort_by, (list, tuple)):
        return [_apply_dir(t) for t in sort_by]
    return [_apply_dir(sort_by)]


@register.inclusion_tag("tables/render_table.html", takes_context=True)
def render_table(
    context: dict[str, Any],
    queryset: QuerySet[Any],
    fields: Iterable[Any],
    *,
    table_id: str = "table",
    per_page: int = 10,
    selectable: bool = True,
    checkbox_name: str = "selected",
    empty_text: str = "Nenhum registro encontrado.",
) -> dict[str, Any]:
    request: HttpRequest = context["request"]

    columns = _normalize_fields(fields)
    sortable_attrs = {c.attr for c in columns if c.sortable and c.attr}

    sort = request.GET.get("sort") or ""
    sort_attr = sort.lstrip("-")
    sort_desc = sort.startswith("-")
    sort_is_valid = bool(sort_attr) and sort_attr in sortable_attrs

    ordered_qs = queryset
    if sort_is_valid:
        col_for_sort = next((c for c in columns if c.attr == sort_attr), None)
        if col_for_sort is not None:
            try:
                ordering_terms = _as_ordering_terms(col_for_sort, desc=sort_desc)
                # Desempate estável para paginação.
                if "pk" not in [t for t in ordering_terms if isinstance(t, str)]:
                    ordering_terms.append("pk")
                ordered_qs = ordered_qs.order_by(*ordering_terms)
            except FieldError:
                # Se o atributo/expressão não for válido para order_by, ignora a ordenação.
                sort_attr = ""
                sort_desc = False

    # Garante ordenação estável para paginação quando não há sort explícito.
    if not ordered_qs.ordered:
        ordered_qs = ordered_qs.order_by("pk")

    paginator = Paginator(ordered_qs, per_page)
    page_number = request.GET.get("page", "1")
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    rendered_columns: list[dict[str, Any]] = []
    for col in columns:
        is_sorted = bool(col.attr) and col.attr == sort_attr
        is_desc = is_sorted and sort_desc
        is_asc = is_sorted and not sort_desc
        can_sort = bool(col.attr) and col.sortable

        next_sort: str | None
        if not can_sort:
            sort_url = None
        elif not is_sorted:
            # 1.º clique: habilita ordenação asc.
            next_sort = col.attr
            sort_url = _build_url(request, updates={"sort": next_sort, "page": 1})
        elif is_asc:
            # 2.º clique: alterna para desc.
            next_sort = f"-{col.attr}"
            sort_url = _build_url(request, updates={"sort": next_sort, "page": 1})
        elif is_desc:
            # 3.º clique: remove ordenação.
            sort_url = _build_url(request, updates={"sort": None, "page": 1})
        else:
            next_sort = col.attr
            sort_url = _build_url(request, updates={"sort": next_sort, "page": 1})

        rendered_columns.append(
            {
                "label": col.label,
                "attr": col.attr,
                "th_class": col.th_class,
                "td_class": col.td_class,
                "sortable": can_sort,
                "is_sorted": is_sorted,
                "is_asc": is_asc,
                "is_desc": is_desc,
                "sort_url": sort_url,
            }
        )

    rows: list[dict[str, Any]] = []
    for obj in page_obj.object_list:
        cells = []
        for col in columns:
            value = _resolve_attr(obj, col.attr)

            # 'bool' em Python é subclasse de 'int', então checamos pelo tipo exato.
            is_boolean = type(value) is bool

            cells.append(
                {
                    "value": value,
                    "td_class": col.td_class,
                    "is_boolean": is_boolean,
                    "bool_value": value if is_boolean else None,
                }
            )
        rows.append({"object": obj, "pk": getattr(obj, "pk", None), "cells": cells})

    prev_url = _build_url(request, updates={"page": page_obj.previous_page_number()}) if page_obj.has_previous() else None
    next_url = _build_url(request, updates={"page": page_obj.next_page_number()}) if page_obj.has_next() else None

    return {
        "table_id": table_id,
        "columns": rendered_columns,
        "rows": rows,
        "page_obj": page_obj,
        "paginator": paginator,
        "is_paginated": paginator.num_pages > 1,
        "prev_url": prev_url,
        "next_url": next_url,
        "selectable": selectable,
        "checkbox_name": checkbox_name,
        "empty_text": empty_text,
    }
