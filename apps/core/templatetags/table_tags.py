from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from django.core.exceptions import FieldError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q, QuerySet
from django.db.models.expressions import BaseExpression
from django.http import HttpRequest
from django.template import Library
from django.urls import NoReverseMatch, reverse
from django.utils.http import urlencode

register = Library()


@dataclass(frozen=True)
class TableColumn:
    label: str
    attr: str | None
    th_class: str = ""
    td_class: str = ""
    sortable: bool = True
    searchable: bool = True
    # Opcional: permite customizar o lookup usado na busca. Ex.: "name", "customer__name".
    search_by: str | None = None
    # Opcional: permite customizar o `order_by` quando `sort=<attr>`.
    # Aceita:
    # - str (campo/lookup),
    # - Expression / OrderBy,
    # - sequência de (str|Expression) para ordenar por múltiplos critérios.
    sort_by: str | BaseExpression | Sequence[str | BaseExpression] | None = None


@dataclass(frozen=True)
class TableAction:
    label: str
    url_name: str | None = None
    url: str | None = None
    # Quais atributos do objeto serão usados como `args` no `reverse`.
    # Ex.: ("pk",) ou ("customer.pk",)
    args: Sequence[str] = ("pk",)
    # kwargs para `reverse`: {"pk": "pk"} ou {"slug": "slug"}.
    kwargs: Mapping[str, str] = field(default_factory=dict)
    a_class: str = "btn btn-ghost btn-xs"
    icon: str = ""
    aria_label: str = ""
    confirm: str | None = None

    # Opcional: permite usar HTMX na ação (ex.: abrir modal, fazer swap parcial, etc.).
    hx_get: str | None = None
    hx_target: str | None = None
    hx_swap: str | None = None
    hx_select: str | None = None
    hx_push_url: str | None = None


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
                    searchable=bool(f.get("searchable", True)),
                    search_by=(str(f.get("search_by")) if f.get("search_by") is not None else None),
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
            searchable = bool(f[6]) if len(f) > 6 else True
            search_by = str(f[7]) if len(f) > 7 and f[7] is not None else None
            normalized.append(
                TableColumn(
                    label=label,
                    attr=attr,
                    th_class=th_class,
                    td_class=td_class,
                    sortable=sortable,
                    searchable=searchable,
                    search_by=search_by,
                    sort_by=sort_by,
                )
            )
            continue

        raise TypeError("Cada coluna deve ser um dict, tuple/list ou TableColumn")

    return normalized


def _normalize_actions(actions: Iterable[Any] | None) -> list[TableAction]:
    if not actions:
        return []

    normalized: list[TableAction] = []
    for a in actions:
        if isinstance(a, TableAction):
            normalized.append(a)
            continue

        if isinstance(a, Mapping):
            kind = str(a.get("kind", "")).strip().lower()

            label = str(a.get("label") or a.get("title") or "")
            url_name = str(a.get("url_name")) if a.get("url_name") is not None else None
            url = str(a.get("url")) if a.get("url") is not None else None

            args = a.get("args")
            if args is None:
                args = ("pk",)
            elif isinstance(args, (list, tuple)):
                args = tuple(str(x) for x in args)
            else:
                args = (str(args),)

            kwargs = a.get("kwargs")
            if isinstance(kwargs, Mapping):
                kwargs = {str(k): str(v) for k, v in kwargs.items()}
            else:
                kwargs = {}

            a_class = str(a.get("a_class") or a.get("btn_class") or "")
            icon = str(a.get("icon") or "")
            aria_label = str(a.get("aria_label") or "")
            confirm = str(a.get("confirm")) if a.get("confirm") is not None else None

            hx_get = str(a.get("hx_get")) if a.get("hx_get") is not None else None
            hx_target = str(a.get("hx_target")) if a.get("hx_target") is not None else None
            hx_swap = str(a.get("hx_swap")) if a.get("hx_swap") is not None else None
            hx_select = str(a.get("hx_select")) if a.get("hx_select") is not None else None
            hx_push_url = str(a.get("hx_push_url")) if a.get("hx_push_url") is not None else None

            # Defaults por tipo (sem sobrescrever se o caller passou explicitamente).
            if kind == "edit":
                if not label:
                    label = "Editar"
                if not icon:
                    icon = "edit"
                if not a_class:
                    a_class = "btn btn-primary btn-sm"
            elif kind == "delete":
                if not label:
                    label = "Excluir"
                if not icon:
                    icon = "delete"
                if not a_class:
                    a_class = "btn btn-error btn-sm text-white"

            normalized.append(
                TableAction(
                    label=label,
                    url_name=url_name,
                    url=url,
                    args=args,
                    kwargs=kwargs,
                    a_class=a_class,
                    icon=icon,
                    aria_label=aria_label,
                    confirm=confirm,
                    hx_get=hx_get,
                    hx_target=hx_target,
                    hx_swap=hx_swap,
                    hx_select=hx_select,
                    hx_push_url=hx_push_url,
                )
            )
            continue

        raise TypeError("Cada ação deve ser um dict ou TableAction")

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
    show_search: bool = True,
    search_param: str = "q",
    search_placeholder: str = "Buscar…",
    actions: Iterable[Any] | None = None,
    actions_label: str = "Ações",
) -> dict[str, Any]:
    request: HttpRequest = context["request"]

    columns = _normalize_fields(fields)
    normalized_actions = _normalize_actions(actions)
    has_actions = bool(normalized_actions)
    search_query = (request.GET.get(search_param) or "").strip()

    filtered_qs = queryset
    if show_search and search_query:
        lookups: list[str] = []
        for col in columns:
            if not col.searchable:
                continue
            lookup = (col.search_by or col.attr or "").strip()
            if not lookup:
                continue
            lookups.append(lookup.replace(".", "__"))

        if lookups:
            q_obj = Q()
            for lookup in lookups:
                q_obj |= Q(**{f"{lookup}__icontains": search_query})
            try:
                filtered_qs = filtered_qs.filter(q_obj)
            except FieldError:
                # Se algum lookup for inválido, ignora a busca.
                search_query = ""

    sortable_attrs = {c.attr for c in columns if c.sortable and c.attr}

    sort = request.GET.get("sort") or ""
    sort_attr = sort.lstrip("-")
    sort_desc = sort.startswith("-")
    sort_is_valid = bool(sort_attr) and sort_attr in sortable_attrs

    ordered_qs = filtered_qs
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
                sort = ""
                sort_attr = ""
                sort_desc = False
    elif sort:
        # sort presente, mas não é permitido pelas colunas.
        sort = ""

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
        row_actions: list[dict[str, Any]] = []
        if has_actions:
            for action in normalized_actions:
                href: str | None = None

                if action.url:
                    # Permite URLs com placeholders simples: "/x/{pk}/edit/".
                    format_ctx: dict[str, Any] = {"pk": getattr(obj, "pk", None)}
                    for path in action.args:
                        format_ctx[path] = _resolve_attr(obj, path)
                    for _, path in action.kwargs.items():
                        format_ctx[path] = _resolve_attr(obj, path)
                    try:
                        href = action.url.format(**format_ctx)
                    except Exception:
                        href = action.url
                elif action.url_name:
                    try:
                        url_args = [_resolve_attr(obj, p) for p in action.args]
                        url_kwargs = {k: _resolve_attr(obj, p) for k, p in action.kwargs.items()}
                        href = reverse(action.url_name, args=url_args, kwargs=url_kwargs)
                    except (NoReverseMatch, AttributeError, TypeError, ValueError):
                        href = None

                if href:
                    hx_get = action.hx_get
                    # Conveniência: se a ação tiver alvo HTMX mas não definiu `hx_get`, usa o próprio `href`.
                    if hx_get in (None, "") and action.hx_target:
                        hx_get = href

                    row_actions.append(
                        {
                            "href": href,
                            "label": action.label,
                            "a_class": action.a_class,
                            "icon": action.icon,
                            "aria_label": action.aria_label or action.label,
                            "confirm": action.confirm,
                            "hx_get": hx_get,
                            "hx_target": action.hx_target,
                            "hx_swap": action.hx_swap,
                            "hx_select": action.hx_select,
                            "hx_push_url": action.hx_push_url,
                        }
                    )

        rows.append({"object": obj, "pk": getattr(obj, "pk", None), "cells": cells, "actions": row_actions})

    prev_url = _build_url(request, updates={"page": page_obj.previous_page_number()}) if page_obj.has_previous() else None
    next_url = _build_url(request, updates={"page": page_obj.next_page_number()}) if page_obj.has_next() else None

    clear_search_url = _build_url(request, updates={search_param: None, "page": 1})

    colspan = len(rendered_columns) + (1 if selectable else 0) + (1 if has_actions else 0)

    return {
        "request": request,
        "table_id": table_id,
        "columns": rendered_columns,
        "rows": rows,
        "has_actions": has_actions,
        "actions_label": actions_label,
        "colspan": colspan,
        "page_obj": page_obj,
        "paginator": paginator,
        "is_paginated": paginator.num_pages > 1,
        "prev_url": prev_url,
        "next_url": next_url,
        "selectable": selectable,
        "checkbox_name": checkbox_name,
        "empty_text": empty_text,
        "show_search": show_search,
        "search_param": search_param,
        "search_query": search_query,
        "search_placeholder": search_placeholder,
        "clear_search_url": clear_search_url,
        "current_sort": sort,
    }
