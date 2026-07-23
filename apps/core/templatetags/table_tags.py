from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, date
from urllib.parse import urlsplit, urlunsplit
from typing import Any

from django.core.exceptions import FieldDoesNotExist, FieldError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import (
    AutoField,
    BigAutoField,
    BigIntegerField,
    Field,
    IntegerField,
    PositiveBigIntegerField,
    PositiveIntegerField,
    PositiveSmallIntegerField,
    Q,
    QuerySet,
    SmallAutoField,
    SmallIntegerField,
)
from django.db.models.expressions import BaseExpression
from django.http import HttpRequest, QueryDict
from django.template import Library
from django.urls import NoReverseMatch, reverse
from django.utils.http import urlencode

from apps.core.infrastructure.search import build_accent_insensitive_lookup
from apps.core.text_normalization import normalize_search_text

register = Library()


@dataclass(frozen=True)
class TableColumn:
    """
    Define a configuração de uma coluna na tabela de dados.

    Attributes:
        label: O texto exibido no cabeçalho da coluna.
        attr: O atributo do objeto (ex: 'nome', 'usuario.email') ou callable
              usado para obter o valor exibido.
        th_class: Classes CSS adicionais para o elemento <th>.
        td_class: Classes CSS adicionais para o elemento <td>.
        sortable: Se True, permite ordenar a tabela por esta coluna.
        searchable: Se True, o valor desta coluna será considerado na busca global.
        search_by: Caminho ou caminhos de lookup personalizados para a busca
                   (ex: 'cliente__nome' ou ('veiculo__placa', 'veiculo__modelo')).
                   Se None, usa o valor de `attr`.
        sort_by: Expressão ou campo personalizado para ordenação no ORM.
                 Pode ser uma string, Expression, ou lista deles.
        format: Identificador de formatação para o frontend (ex: 'cnpj', 'money').
        cell_template: Template opcional para renderizacao customizada da celula.
        mobile_stack: Em cards mobile, empilha rotulo e valor verticalmente.
    """

    label: str
    attr: str | Callable[[Any], Any] | None
    th_class: str = ""
    td_class: str = ""
    sortable: bool = True
    searchable: bool = True
    search_by: str | Sequence[str] | None = None
    sort_by: str | BaseExpression | Sequence[str | BaseExpression] | None = None
    format: str | None = None
    cell_template: str = ""
    mobile_stack: bool = False


@dataclass(frozen=True)
class TableAction:
    """
    Define uma ação (botão/link) disponível para cada linha da tabela.

    Attributes:
        label: O texto do botão ou tooltip.
        url_name: O nome da URL (reverse) do Django.
        url: Uma string de URL direta (pode usar placeholders como {pk}).
        args: Lista de atributos do objeto a serem passados como args para a URL.
        kwargs: Dicionário de atributos a serem passados como kwargs para a URL.
        a_class: Classes CSS para o elemento <a>.
        icon: Nome do ícone (para bibliotecas como Material Icons).
        aria_label: Texto para acessibilidade.
        confirm: Se preenchido, exibe um alerta de confirmação JS ao clicar.
        hx_get, hx_target, etc.: Atributos para integração com HTMX.
    """

    label: str
    url_name: str | None = None
    url: str | None = None
    args: Sequence[str] = ("pk",)
    kwargs: dict[str, str] = field(default_factory=dict)
    a_class: str = "btn btn-ghost btn-xs"
    icon: str = ""
    aria_label: str = ""
    confirm: str | None = None
    hx_get: str | None = None
    hx_target: str | None = None
    hx_swap: str | None = None
    hx_select: str | None = None
    hx_push_url: str | None = None
    preserve_current_url_as_next: bool = False
    visible: bool | Callable[[Any], bool] = True


def _normalize_columns(fields: Sequence[TableColumn | dict[str, Any]]) -> list[TableColumn]:
    normalized: list[TableColumn] = []
    for column in fields:
        if isinstance(column, TableColumn):
            normalized.append(column)
        else:
            normalized.append(TableColumn(**column))
    return normalized


def _normalize_actions(actions: Sequence[TableAction | dict[str, Any]] | None) -> list[TableAction]:
    normalized: list[TableAction] = []
    for action in actions or []:
        if isinstance(action, TableAction):
            normalized.append(action)
            continue

        action_dict = dict(action)
        kind = action_dict.pop("kind", None)
        if kind == "delete":
            normalized.append(TableAction(label=action_dict.pop("label", "Excluir"), icon=action_dict.pop("icon", "delete"), a_class=action_dict.pop("a_class", "btn-table-delete"), aria_label=action_dict.pop("aria_label", "Excluir registro"), **action_dict))
        elif kind == "edit":
            normalized.append(TableAction(label=action_dict.pop("label", "Editar"), icon=action_dict.pop("icon", "edit"), a_class=action_dict.pop("a_class", "btn-table-edit"), aria_label=action_dict.pop("aria_label", "Editar registro"), **action_dict))
        elif kind == "view":
            normalized.append(TableAction(label=action_dict.pop("label", "Visualizar"), icon=action_dict.pop("icon", "visibility"), a_class=action_dict.pop("a_class", "btn-table-view"), aria_label=action_dict.pop("aria_label", "Visualizar registro"), **action_dict))
        else:
            normalized.append(TableAction(**action_dict))
    return normalized


def _resolve_attr(obj: Any, attr: str | Callable[[Any], Any] | None) -> Any:
    """
    Navega recursivamente pelos atributos de um objeto usando notação de ponto.
    Suporta atributos simples e chamáveis (métodos sem argumentos).
    """
    if attr in (None, ""):
        return obj
    if callable(attr):
        return attr(obj)
    if not isinstance(attr, str):
        return attr

    value: Any = obj
    for part in attr.split("."):
        try:
            value = getattr(value, part)
        except AttributeError:
            return None

        if callable(value):
            value = value()

    if isinstance(value, (datetime, date)):
        return value.strftime("%d/%m/%Y")

    return value if value is not None else ""


def _build_url(request: HttpRequest, *, updates: dict[str, Any]) -> str:
    """
    Reconstrói a URL atual atualizando ou removendo parâmetros da query string.
    Útil para links de paginação e ordenação mantendo os filtros existentes.
    """
    params = request.GET.copy()
    for key, value in updates.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = str(value)

    qs = urlencode(params, doseq=True)
    return f"{request.path}?{qs}" if qs else request.path


@dataclass(frozen=True)
class _TableSearchLookup:
    lookup: str
    field: Field | None = None


def _iter_string_search_sources(source: str | Sequence[str] | None) -> list[str]:
    if source is None:
        return []
    if isinstance(source, str):
        return [source]
    return [item for item in source if isinstance(item, str)]


def _resolve_model_field(model: type[Any], lookup_part: str) -> tuple[Field | Any | None, bool]:
    try:
        return model._meta.get_field(lookup_part), False
    except FieldDoesNotExist:
        for field in model._meta.get_fields():
            if getattr(field, "attname", None) == lookup_part:
                return field, True
    return None, False


def _resolve_search_lookup(model: type[Any], lookup: str, *, annotations: set[str]) -> _TableSearchLookup | None:
    if "__" not in lookup and lookup in annotations:
        return _TableSearchLookup(lookup=lookup)

    current_model = model
    parts = lookup.split("__")
    resolved_field: Field | None = None

    for index, part in enumerate(parts):
        field, matched_attname = _resolve_model_field(current_model, part)
        if field is None:
            return None

        is_last = index == len(parts) - 1
        if is_last:
            if matched_attname:
                resolved_field = field if isinstance(field, Field) else None
                break

            if getattr(field, "is_relation", False):
                return None

            resolved_field = field if isinstance(field, Field) else None
            break

        if matched_attname or not getattr(field, "is_relation", False) or getattr(field, "related_model", None) is None:
            return None

        current_model = field.related_model

    return _TableSearchLookup(lookup=lookup, field=resolved_field)


def _get_search_lookups(qs: QuerySet[Any], *, columns: Sequence[TableColumn]) -> list[_TableSearchLookup]:
    annotations = set(getattr(qs.query, "annotations", {}).keys())
    lookups: list[_TableSearchLookup] = []
    seen: set[str] = set()

    for col in columns:
        if not col.searchable:
            continue

        lookup_source = col.search_by if col.search_by is not None else col.attr
        for raw_lookup in _iter_string_search_sources(lookup_source):
            lookup = raw_lookup.strip().replace(".", "__")
            if not lookup or lookup in seen:
                continue

            resolved_lookup = _resolve_search_lookup(qs.model, lookup, annotations=annotations)
            if resolved_lookup is None:
                continue

            seen.add(lookup)
            lookups.append(resolved_lookup)

    return lookups


def _matching_choice_values(field: Field | None, *, search_query: str) -> list[Any]:
    if field is None or not getattr(field, "flatchoices", None):
        return []

    normalized_query = normalize_search_text(search_query)
    if not normalized_query:
        return []

    matched_values: list[Any] = []
    for value, label in field.flatchoices:
        if value in (None, ""):
            continue
        if normalized_query in normalize_search_text(label):
            matched_values.append(value)

    return matched_values


def _parse_integer_search_value(search_query: str) -> int | None:
    normalized = search_query.strip()
    if not normalized:
        return None

    compact = normalized.replace(" ", "").replace(".", "").replace(",", "")
    if not compact.isdigit():
        return None

    try:
        return int(compact)
    except ValueError:
        return None


def _as_ordering_terms(col: TableColumn, *, desc: bool) -> list[str | BaseExpression]:
    """
    C onverte a configuração de ordenação de uma coluna em termos compatíveis
    com o método `.order_by()` do Django ORM, aplicando a direção(asc/desc).
    """

    def _apply_dir(term: str | BaseExpression) -> str | BaseExpression:
        if isinstance(term, str):
            return f"-{term}" if desc else term
        return term.desc() if desc else term.asc()

    sort_by = col.sort_by if col.sort_by is not None else col.attr
    if sort_by is None:
        return []

    if isinstance(sort_by, (list, tuple)):
        return [_apply_dir(t) for t in sort_by]
    return [_apply_dir(sort_by)]


def _get_search_query(request: HttpRequest, *, show_search: bool, search_param: str) -> str:
    """
    Extrai o termo de busca atual dos parâmetros GET da requisição.
    """
    if not show_search:
        return ""
    return (request.GET.get(search_param) or "").strip()


def _apply_search(
    qs: QuerySet[Any],
    *,
    columns: Sequence[TableColumn],
    search_query: str,
) -> tuple[QuerySet[Any], str]:
    """
    Filtra o QuerySet aplicando uma busca textual (icontains) em todas as
    colunas marcadas como `searchable`. Retorna o QuerySet filtrado e o termo usado.
    """
    if not search_query:
        return qs, search_query

    normalized = search_query.strip().lower()

    # Como eu defini nas células da tabela para usarem "Sim" e "Não" ao invés de "True" e "False", estou mudando a pesquisa para usar esses termos.
    truthy_terms = {"sim"}
    falsy_terms = {"nao", "não"}

    bool_term: bool | None = None
    if normalized in truthy_terms:
        bool_term = True
    elif normalized in falsy_terms:
        bool_term = False

    lookups = _get_search_lookups(qs, columns=columns)

    if not lookups:
        return qs, search_query

    integer_search_value = _parse_integer_search_value(search_query)
    integer_field_types = (
        AutoField,
        BigAutoField,
        SmallAutoField,
        IntegerField,
        BigIntegerField,
        SmallIntegerField,
        PositiveIntegerField,
        PositiveSmallIntegerField,
        PositiveBigIntegerField,
    )

    query_clauses: list[Q] = []
    for lookup_spec in lookups:
        lookup = lookup_spec.lookup
        field = lookup_spec.field

        if integer_search_value is not None and isinstance(field, integer_field_types):
            exact_int_clause = Q(**{f"{lookup}__exact": integer_search_value})
            try:
                qs.filter(exact_int_clause)
            except FieldError:
                pass
            else:
                query_clauses.append(exact_int_clause)

        if bool_term is not None:
            exact_clause = Q(**{f"{lookup}__exact": bool_term})
            try:
                qs.filter(exact_clause)
            except FieldError:
                pass
            else:
                query_clauses.append(exact_clause)

        for choice_value in _matching_choice_values(field, search_query=search_query):
            choice_clause = Q(**{f"{lookup}__exact": choice_value})
            try:
                qs.filter(choice_clause)
            except FieldError:
                continue
            query_clauses.append(choice_clause)

        contains_clause = Q(**{build_accent_insensitive_lookup(lookup): search_query})
        try:
            qs.filter(contains_clause)
        except FieldError:
            continue
        query_clauses.append(contains_clause)

    if not query_clauses:
        return qs, search_query

    combined_query = query_clauses[0]
    for clause in query_clauses[1:]:
        combined_query |= clause

    return qs.filter(combined_query), search_query


def _parse_sort(request: HttpRequest, *, sortable_attrs: set[str]) -> tuple[str, str, bool, bool]:
    """
    Analisa os parâmetros GET para determinar a ordenação solicitada.
    Retorna o valor bruto, o atributo, se é descendente e se é válido.
    """
    sort = request.GET.get("sort") or ""
    sort_attr = sort.lstrip("-")
    sort_desc = sort.startswith("-")
    sort_is_valid = bool(sort_attr) and sort_attr in sortable_attrs
    return sort, sort_attr, sort_desc, sort_is_valid


def _apply_sort(
    qs: QuerySet[Any],
    *,
    columns: Sequence[TableColumn],
    sort: str,
    sort_attr: str,
    sort_desc: bool,
    sort_is_valid: bool,
) -> tuple[QuerySet[Any], str, str, bool]:
    """
    Aplica a cláusula `order_by` ao QuerySet com base na coluna selecionada.
    Adiciona `pk` como critério de desempate para garantir determinismo.
    """
    if not sort_is_valid:
        return qs, "" if sort else sort, "", False

    col_for_sort = next((c for c in columns if c.attr == sort_attr), None)
    if col_for_sort is None:
        return qs, "", "", False

    try:
        ordering_terms = _as_ordering_terms(col_for_sort, desc=sort_desc)
        if "pk" not in [t for t in ordering_terms if isinstance(t, str)]:
            ordering_terms.append("pk")
        return qs.order_by(*ordering_terms), sort, sort_attr, sort_desc
    except FieldError:
        return qs, "", "", False


def _ensure_stable_ordering(qs: QuerySet[Any]) -> QuerySet[Any]:
    """
    Garante que o QuerySet tenha alguma ordenação definida (padrão PK)
    para evitar inconsistências na paginação.
    """
    if not qs.ordered:
        return qs.order_by("pk")
    return qs


def _paginate(qs: QuerySet[Any], *, per_page: int, page_number: str) -> tuple[Any, Paginator]:
    """
    Pagina o QuerySet. Trata casos de página inválida (retorna a primeira)
    ou página vazia (retorna a última).
    """
    paginator = Paginator(qs, per_page)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    return page_obj, paginator


def _apply_search_to_sequence(items: Sequence[Any], *, columns: Sequence[TableColumn], search_query: str) -> tuple[list[Any], str]:
    if not search_query:
        return list(items), search_query

    normalized = normalize_search_text(search_query)
    truthy_terms = {"sim"}
    falsy_terms = {"nao", "não"}

    bool_term: bool | None = None
    if normalized in truthy_terms:
        bool_term = True
    elif normalized in falsy_terms:
        bool_term = False

    searchable_sources: list[list[str | Callable[[Any], Any]]] = []
    for col in columns:
        if not col.searchable:
            continue

        if col.search_by is None:
            if col.attr in (None, ""):
                continue
            sources: list[str | Callable[[Any], Any]] = [col.attr]
        else:
            sources = []
            for raw_lookup in _iter_string_search_sources(col.search_by):
                lookup = raw_lookup.strip()
                if not lookup:
                    continue
                sources.append(lookup.replace("__", "."))
            if not sources:
                continue

        searchable_sources.append(sources)

    if not searchable_sources:
        return list(items), search_query

    filtered_items: list[Any] = []
    for item in items:
        matched = False
        for sources in searchable_sources:
            for source in sources:
                value = _resolve_attr(item, source)
                if bool_term is not None and type(value) is bool and value is bool_term:
                    filtered_items.append(item)
                    matched = True
                    break
                if value is None:
                    continue
                if normalized in normalize_search_text(value):
                    filtered_items.append(item)
                    matched = True
                    break
            if matched:
                break

    return filtered_items, search_query


def _apply_sort_to_sequence(items: Sequence[Any], *, columns: Sequence[TableColumn], sort_attr: str, sort_desc: bool, sort_is_valid: bool) -> tuple[list[Any], str, str, bool]:
    if not sort_is_valid:
        return list(items), "", "", False

    col_for_sort = next((c for c in columns if c.attr == sort_attr), None)
    if col_for_sort is None:
        return list(items), "", "", False

    def _normalize(value: Any) -> tuple[int, Any]:
        if value is None or value == "":
            return (1, "")
        if isinstance(value, bool):
            return (0, int(value))
        if isinstance(value, (datetime, date)):
            return (0, value)
        return (0, str(value).lower())

    sorted_items = sorted(list(items), key=lambda item: _normalize(_resolve_attr(item, col_for_sort.attr)), reverse=sort_desc)
    return sorted_items, sort_attr if not sort_desc else f"-{sort_attr}", sort_attr, sort_desc


def _paginate_sequence(items: Sequence[Any], *, per_page: int, page_number: str) -> tuple[Any, Paginator]:
    paginator = Paginator(list(items), per_page)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    return page_obj, paginator


def _render_columns(
    *,
    columns: Sequence[TableColumn],
    request: HttpRequest,
    sort_attr: str,
    sort_desc: bool,
) -> list[dict[str, Any]]:
    """
    Prepara os dados dos cabeçalhos das colunas para o template, incluindo
    a lógica de URLs para alternar a ordenação (Asc -> Desc -> None).
    """
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
            next_sort = col.attr
            sort_url = _build_url(request, updates={"sort": next_sort, "page": 1})
        elif is_asc:
            next_sort = f"-{col.attr}"
            sort_url = _build_url(request, updates={"sort": next_sort, "page": 1})
        elif is_desc:
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

    return rendered_columns


def _resolve_action_href(obj: Any, action: TableAction) -> str | None:
    """
    Gera a URL final para uma ação em uma linha específica, resolvendo
    parâmetros dinâmicos (args/kwargs) baseados nos dados do objeto.
    """
    if action.url:
        format_ctx: dict[str, Any] = {"pk": getattr(obj, "pk", None)}
        for path in action.args:
            format_ctx[path] = _resolve_attr(obj, path)
        for _, path in action.kwargs.items():
            format_ctx[path] = _resolve_attr(obj, path)
        try:
            return action.url.format(**format_ctx)
        except Exception:
            return action.url

    if action.url_name:
        try:
            url_args = [_resolve_attr(obj, p) for p in action.args]
            url_kwargs = {k: _resolve_attr(obj, p) for k, p in action.kwargs.items()}
            return reverse(action.url_name, args=url_args, kwargs=url_kwargs)
        except (NoReverseMatch, AttributeError, TypeError, ValueError):
            return None

    return None


def _append_query_param(url: str, *, param_name: str, value: str) -> str:
    normalized_value = str(value or "").strip()
    if not normalized_value:
        return url

    parsed_url = urlsplit(url)
    query_params = QueryDict(parsed_url.query, mutable=True)
    query_params[param_name] = normalized_value
    encoded_query = query_params.urlencode()
    return urlunsplit((parsed_url.scheme, parsed_url.netloc, parsed_url.path, encoded_query, parsed_url.fragment))


def _render_rows(
    *,
    page_obj: Any,
    columns: Sequence[TableColumn],
    actions: Sequence[TableAction],
    request: HttpRequest,
    selected_values: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Transforma os objetos da página atual em uma estrutura de lista de dicionários
    pronta para renderização, processando os valores das células e links de ação.
    """
    rows: list[dict[str, Any]] = []
    has_actions = bool(actions)
    selected_keys = selected_values or set()

    for obj in page_obj.object_list:
        obj_pk = getattr(obj, "pk", None)
        cells: list[dict[str, Any]] = []
        for col in columns:
            value = _resolve_attr(obj, col.attr)
            is_boolean = type(value) is bool

            cells.append(
                {
                    "label": col.label,
                    "value": value,
                    "td_class": col.td_class,
                    "cell_template": col.cell_template,
                    "mobile_stack": col.mobile_stack,
                    "is_boolean": is_boolean,
                    "bool_value": value if is_boolean else None,
                    "format": col.format,
                }
            )

        row_actions: list[dict[str, Any]] = []
        if has_actions:
            for action in actions:
                is_visible = action.visible(obj) if callable(action.visible) else bool(action.visible)
                if not is_visible:
                    continue

                href = _resolve_action_href(obj, action)
                if not href:
                    continue

                if action.preserve_current_url_as_next:
                    href = _append_query_param(href, param_name="next", value=request.get_full_path())

                hx_get = action.hx_get
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

        rows.append(
            {
                "object": obj,
                "pk": obj_pk,
                "parent_pk": getattr(obj, "parent_id", None),
                "cells": cells,
                "actions": row_actions,
                "is_selected": str(obj_pk) in selected_keys,
            }
        )

    return rows


def _build_sort_options(*, columns: Sequence[TableColumn], current_sort: str) -> list[dict[str, Any]]:
    """
    Gera a lista de opções para o dropdown de ordenação (interface mobile),
    criando pares de ordenação Ascendente (A-Z) e Descendente (Z-A).
    """
    options: list[dict[str, Any]] = [
        {"value": "", "label": "Sem ordenação", "selected": current_sort in (None, "")},
    ]

    for col in columns:
        if not col.attr or not col.sortable:
            continue

        asc_value = col.attr
        desc_value = f"-{col.attr}"

        options.append({"value": asc_value, "label": f"{col.label} (A-Z)", "selected": current_sort == asc_value})
        options.append({"value": desc_value, "label": f"{col.label} (Z-A)", "selected": current_sort == desc_value})

    return options


def _normalize_filter_param_names(filter_param_names: str | Sequence[str] | None) -> list[str]:
    """
    Normaliza a configuração de nomes de parâmetros de filtro.

    Aceita string separada por vírgula (uso em templates) ou sequência de strings
    (uso em Python), removendo vazios e duplicados.
    """
    if not filter_param_names:
        return []

    if isinstance(filter_param_names, str):
        raw_param_names = filter_param_names.split(",")
    else:
        raw_param_names = [str(name) for name in filter_param_names]

    normalized: list[str] = []
    for raw_name in raw_param_names:
        param_name = raw_name.strip()
        if not param_name or param_name in normalized:
            continue
        normalized.append(param_name)

    return normalized


def _copy_parent_context(context: Any) -> dict[str, Any]:
    """
    Copia o contexto pai para manter variáveis extras no inclusion tag.

    Quando chamado a partir de templates Django, `context` é um `Context`
    e precisa ser achatado com `.flatten()`. Em testes diretos, pode ser um
    dicionário simples.
    """
    flatten = getattr(context, "flatten", None)
    if callable(flatten):
        return dict(flatten())
    return dict(context)


@register.inclusion_tag("tables/main_table.html", takes_context=True)
def render_table(
    context: Any,
    queryset: QuerySet[Any] | Sequence[Any],
    fields: Sequence[TableColumn],
    *,
    table_id: str = "table",
    per_page: int = 10,
    selectable: bool = True,
    checkbox_name: str = "selected",
    empty_text: str = "Nenhum registro encontrado.",
    show_search: bool = True,
    search_param: str = "q",
    search_placeholder: str = "Buscar…",
    actions: Sequence[TableAction] | None = None,
    actions_label: str = "Ações",
    filter_fields_template: str = "",
    filter_button_label: str = "Filtro",
    filter_panel_title: str = "Filtrar resultados",
    filter_param_names: str | Sequence[str] = (),
    summary_template: str = "",
    controls_actions_template: str = "",
    footer_template: str = "",
    show_controls: bool = True,
    preserve_selection: bool = False,
    hierarchical_selection: bool = False,
    htmx_push_url: bool = True,
    disable_pagination_when_filtered: bool = False,
) -> dict[str, Any]:
    """
    Inclusion tag principal para renderizar uma tabela de dados completa.

    Processa busca, ordenação, paginação e ações antes de enviar o contexto
    para o template `tables/main_table.html`.

    Args:
        context: Contexto do template Django (injetado automaticamente).
        queryset: O QuerySet base contendo os dados.
        fields: Lista de objetos TableColumn definindo as colunas.
        table_id: ID HTML único para a tabela (usado em HTMX/DOM).
        per_page: Número de registros por página.
        selectable: Se True, exibe checkboxes para seleção de linhas.
        checkbox_name: O atributo 'name' dos inputs checkbox.
        empty_text: Mensagem exibida quando não há registros.
        show_search: Se True, exibe a barra de busca.
        search_param: Nome do parâmetro GET para a busca (default: 'q').
        search_placeholder: Placeholder do input de busca.
        actions: Lista de objetos TableAction definindo botões por linha.
        actions_label: Título da coluna de ações.
        filter_fields_template: Caminho de template opcional para campos de filtro extras.
        filter_button_label: Texto do botão de abrir painel de filtros.
        filter_panel_title: Título exibido no painel de filtros.
        filter_param_names: Nomes dos parâmetros GET usados pelos filtros extras.
            Pode ser string separada por vírgula (ex.: "city,state") ou sequência.
        summary_template: Caminho opcional de template para renderizar um resumo
            acima dos controles e da tabela.
        controls_actions_template: Caminho opcional de template para renderizar
            ações extras à direita da linha de controles.
        footer_template: Caminho opcional de template para renderizar conteúdo
            abaixo da tabela e da paginação.
        show_controls: Se False, oculta os controles superiores (busca/ordenação/filtros).
        preserve_selection: Se True, mantém checkboxes de linha marcados com base na query string atual.
            Também marca IDs presentes em `preselected_row_ids` ou `highlighted_row_ids` no contexto.
        hierarchical_selection: Se True, sincroniza seleção pai/filhos via metadados de hierarquia.
        htmx_push_url: Se True, atualiza a URL do navegador durante interações HTMX da tabela.
        disable_pagination_when_filtered: Se True, remove a paginação quando houver filtros extras ativos.
    """
    parent_context = _copy_parent_context(context)
    request: HttpRequest = parent_context["request"]
    is_htmx = bool(getattr(request, "htmx", False))

    filter_fields_template = (filter_fields_template or "").strip()
    show_filter_controls = bool(filter_fields_template)
    normalized_filter_param_names = _normalize_filter_param_names(filter_param_names)

    columns = _normalize_columns(fields)
    action_list = _normalize_actions(actions)
    has_actions = bool(action_list)

    is_queryset = isinstance(queryset, QuerySet)

    search_query = _get_search_query(request, show_search=show_search, search_param=search_param)
    if is_queryset:
        filtered_items, search_query = _apply_search(queryset, columns=columns, search_query=search_query)
    else:
        filtered_items, search_query = _apply_search_to_sequence(queryset, columns=columns, search_query=search_query)

    sortable_attrs = {c.attr for c in columns if c.sortable and c.attr}
    sort, sort_attr, sort_desc, sort_is_valid = _parse_sort(request, sortable_attrs=sortable_attrs)

    if is_queryset:
        ordered_items, sort, sort_attr, sort_desc = _apply_sort(
            filtered_items,
            columns=columns,
            sort=sort,
            sort_attr=sort_attr,
            sort_desc=sort_desc,
            sort_is_valid=sort_is_valid,
        )
        ordered_items = _ensure_stable_ordering(ordered_items)
    else:
        ordered_items, sort, sort_attr, sort_desc = _apply_sort_to_sequence(filtered_items, columns=columns, sort_attr=sort_attr, sort_desc=sort_desc, sort_is_valid=sort_is_valid)

    has_active_filters = show_filter_controls and any(str(value).strip() != "" for param_name in normalized_filter_param_names for value in request.GET.getlist(param_name))

    effective_per_page = per_page
    if disable_pagination_when_filtered and has_active_filters:
        effective_per_page = max(len(ordered_items), 1) if not is_queryset else max(ordered_items.count(), 1)

    page_number = request.GET.get("page", "1")
    if is_queryset:
        page_obj, paginator = _paginate(ordered_items, per_page=effective_per_page, page_number=page_number)
    else:
        page_obj, paginator = _paginate_sequence(ordered_items, per_page=effective_per_page, page_number=page_number)

    rendered_columns = _render_columns(columns=columns, request=request, sort_attr=sort_attr, sort_desc=sort_desc)
    selected_values: set[str] = set()
    if selectable and preserve_selection:
        selected_values = {str(raw_value) for raw_value in request.GET.getlist(checkbox_name) if str(raw_value).strip() != ""}
        # Allow views to pre-check rows via context (e.g. members already in a group).
        context_preselected = parent_context.get("preselected_row_ids")
        if context_preselected is None:
            context_preselected = parent_context.get("highlighted_row_ids")
        if context_preselected:
            selected_values.update(str(row_id) for row_id in context_preselected if str(row_id).strip() != "")

    rows = _render_rows(page_obj=page_obj, columns=columns, actions=action_list, request=request, selected_values=selected_values)

    prev_url = _build_url(request, updates={"page": page_obj.previous_page_number()}) if page_obj.has_previous() else None
    next_url = _build_url(request, updates={"page": page_obj.next_page_number()}) if page_obj.has_next() else None

    clear_search_url = _build_url(request, updates={search_param: None, "page": 1})

    clear_filter_url = None
    if show_filter_controls and normalized_filter_param_names:
        clear_filter_updates: dict[str, Any] = {**{param_name: None for param_name in normalized_filter_param_names}, "page": 1}
        clear_filter_url = _build_url(request, updates=clear_filter_updates)

    colspan = len(rendered_columns) + (1 if selectable else 0) + (1 if has_actions else 0)

    return {
        **parent_context,
        "request": request,
        "is_htmx": is_htmx,
        "table_id": table_id,
        "columns": rendered_columns,
        "rows": rows,
        "has_actions": has_actions,
        "actions_label": actions_label,
        "show_controls": show_controls,
        "colspan": colspan,
        "page_obj": page_obj,
        "paginator": paginator,
        "is_paginated": paginator.num_pages > 1,
        "prev_url": prev_url,
        "next_url": next_url,
        "selectable": selectable,
        "checkbox_name": checkbox_name,
        "hierarchical_selection": hierarchical_selection,
        "empty_text": empty_text,
        "show_search": show_search,
        "search_param": search_param,
        "search_query": search_query,
        "search_placeholder": search_placeholder,
        "clear_search_url": clear_search_url,
        "current_sort": sort,
        "sort_options": _build_sort_options(columns=columns, current_sort=sort),
        "show_filter_controls": show_filter_controls,
        "filter_fields_template": filter_fields_template,
        "filter_button_label": filter_button_label,
        "filter_panel_title": filter_panel_title,
        "summary_template": (summary_template or "").strip(),
        "controls_actions_template": (controls_actions_template or "").strip(),
        "footer_template": (footer_template or "").strip(),
        "has_active_filters": has_active_filters,
        "clear_filter_url": clear_filter_url,
        "htmx_target": f"#{table_id}-content",
        "htmx_select": f"#{table_id}-content",
        "htmx_swap": "outerHTML",
        "htmx_push_url": "true" if htmx_push_url else "false",
    }
