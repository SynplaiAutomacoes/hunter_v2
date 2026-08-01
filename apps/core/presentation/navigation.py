from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlencode

from django.http import HttpRequest
from django.urls import reverse

from apps.workshops.context_processors import active_workshops


VisibilityPredicate = Callable[[HttpRequest, dict[str, Any]], bool]


def _is_director_or_manager(request: HttpRequest, flags: dict[str, Any]) -> bool:
    return bool(flags.get("active_workshop_is_director") or flags.get("active_workshop_is_manager"))


BUDGET_CREATE_FAVORITE_PAGE: dict[str, Any] = {"label": "Novo Orçamento", "view_name": "budget:budget_create"}
CREATE_CLIENT_FAVORITE_PAGE: dict[str, Any] = {"label": "Criar cliente", "view_name": "customer:customer_create"}
COLLABORATOR_CREATE_FAVORITE_PAGE: dict[str, Any] = {"label": "Criar colaborador", "view_name": "collaborators:collaborator_create"}
SUPPLIER_CREATE_FAVORITE_PAGE: dict[str, Any] = {"label": "Criar fornecedor", "view_name": "suppliers:supplier_create"}
PRODUCT_CREATE_FAVORITE_PAGE: dict[str, Any] = {"label": "Novo Produto", "view_name": "catalog:product_create"}
SERVICE_CREATE_FAVORITE_PAGE: dict[str, Any] = {"label": "Novo Serviço", "view_name": "catalog:services_create"}
KIT_CREATE_FAVORITE_PAGE: dict[str, Any] = {"label": "Novo Kit", "view_name": "catalog:kits_create"}
CATALOG_GROUP_CREATE_FAVORITE_PAGE: dict[str, Any] = {"label": "Criar grupo", "view_name": "catalog:group_create"}
CHECKLIST_CREATE_FAVORITE_PAGE: dict[str, Any] = {"label": "Novo Checklist", "view_name": "checklist:checklist_create"}
APPOINTMENT_CREATE_FAVORITE_PAGE: dict[str, Any] = {"label": "Novo agendamento", "view_name": "scheduling:appointment_calendar", "query": {"open": "create"}}
STOCK_IMPORT_CREATE_FAVORITE_PAGE: dict[str, Any] = {"label": "Nova importação", "view_name": "stock:import"}
FINANCIAL_MOVEMENT_CREATE_FAVORITE_PAGE: dict[str, Any] = {"label": "Nova Movimentação Financeira", "view_name": "finance:financial_movement_create"}


NAVBAR_MENU_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {"label": "Orçamentos", "view_name": "budget:budget_list", "favoritable": False},
    {"label": "Ordens de serviço", "view_name": "workorder:workorder_list", "favoritable": False},
    {"label": "Agendamentos", "view_name": "scheduling:appointment_calendar", "favoritable": False},
    {
        "label": "Estoque",
        "items": (
            {"label": "Consulta no estoque", "view_name": "stock:stock_inquiry"},
            {"label": "Transferência", "view_name": "stock:transfer"},
            {"label": "Importar itens", "view_name": "stock:stock_list"},
            {"label": "Aprovação", "view_name": "stock:approvals"},
            {"label": "Reabastecimento", "view_name": "stock:replenishment"},
            {"label": "Relatório", "view_name": "stock:report"},
            {"label": "Movimentações", "view_name": "stock:movements"},
            {"label": "Alertas", "view_name": "stock:alerts"},
        ),
    },
    {
        "label": "Financeiro",
        "items": (
            {"label": "Emitir nota", "view_name": "finance:emission_create"},
            {"label": "Central de Notas", "view_name": "finance:issued_documents_list"},
            {"label": "Movimentação Financeira", "view_name": "finance:reports_home"},
            {"label": "Folha de Pagamento", "view_name": "finance:payroll_list"},
            {"label": "Apuração de Comissões", "view_name": "finance:commission_report"},
            {"label": "Conta Bancária", "view_name": "finance:bank_account_list"},
            {"label": "Formas de Pagamento", "view_name": "finance:payment_methods_list"},
            {"label": "Grupos Financeiros", "view_name": "finance:financial_groups_list"},
            {"label": "Classe de Imposto", "view_name": "finance:tax_class_list"},
            {"label": "Gerar DRE", "view_name": "finance:dre_report"},
            {"label": "Fluxo de Contas", "view_name": "finance:cash_flow"},
        ),
    },
    {
        "label": "Cadastros",
        "items": (
            {"label": "Cliente", "view_name": "customer:customer_list"},
            {"label": "Mensagens WhatsApp", "view_name": "messaging:message_template_list"},
            {"label": "Grupos de Mensagens", "view_name": "messaging:customer_message_group_list"},
            {"label": "Colaborador", "view_name": "collaborators:collaborator_list"},
            {"label": "Fornecedor", "view_name": "suppliers:supplier_list"},
            {"label": "Produto", "view_name": "catalog:product_list"},
            {"label": "Serviço", "view_name": "catalog:services_list"},
            {"label": "Kit", "view_name": "catalog:kits_list"},
            {"label": "Grupo", "view_name": "catalog:group_list"},
            {"label": "Checklist", "view_name": "checklist:checklist_list"},
            {"label": "Planos de Revisão", "view_name": "workshops:review_plan_list"},
        ),
    },
    {
        "label": "Gestão",
        "items": (
            {"label": "Gerenciar Oficinas", "view_name": "workshops:list"},
            {"label": "Gerenciar Permissões", "view_name": "iam:role_list"},
            {"label": "Histórico de Emissões", "view_name": "workshops:emission_history", "visible_if": _is_director_or_manager},
            {"label": "Custo Mensal da Oficina", "view_name": "workshops:workshop_cost_list"},
            {"label": "Perguntas investigativas", "view_name": "quote:investigative_question_list"},
            {"label": "Avaliações", "view_name": "messaging:satisfaction_review_list"},
        ),
    },
)

EXTRA_FAVORITABLE_PAGE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    BUDGET_CREATE_FAVORITE_PAGE,
    CREATE_CLIENT_FAVORITE_PAGE,
    COLLABORATOR_CREATE_FAVORITE_PAGE,
    SUPPLIER_CREATE_FAVORITE_PAGE,
    PRODUCT_CREATE_FAVORITE_PAGE,
    SERVICE_CREATE_FAVORITE_PAGE,
    KIT_CREATE_FAVORITE_PAGE,
    CATALOG_GROUP_CREATE_FAVORITE_PAGE,
    CHECKLIST_CREATE_FAVORITE_PAGE,
    APPOINTMENT_CREATE_FAVORITE_PAGE,
    STOCK_IMPORT_CREATE_FAVORITE_PAGE,
    FINANCIAL_MOVEMENT_CREATE_FAVORITE_PAGE,
)


def _resolve_href(entry_definition: dict[str, Any]) -> str:
    href = reverse(entry_definition["view_name"])
    query = entry_definition.get("query")
    if not query:
        return href
    return f"{href}?{urlencode(query, doseq=True)}"


def build_favoritable_page(entry_definition: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": entry_definition["label"],
        "href": _resolve_href(entry_definition),
        "favoritable": bool(entry_definition.get("favoritable", True)),
    }


def _is_visible(entry_definition: dict[str, Any], *, request: HttpRequest, flags: dict[str, Any]) -> bool:
    visible_if: VisibilityPredicate | None = entry_definition.get("visible_if")
    if visible_if is None:
        return True
    return bool(visible_if(request, flags))


def _build_navbar_payload(request: HttpRequest) -> dict[str, Any]:
    cached_payload = getattr(request, "_navbar_navigation_payload", None)
    if cached_payload is not None:
        return cached_payload

    flags = active_workshops(request)
    menus: list[dict[str, Any]] = []
    pages_by_url: dict[str, dict[str, str]] = {}

    for menu_definition in NAVBAR_MENU_DEFINITIONS:
        if not _is_visible(menu_definition, request=request, flags=flags):
            continue

        item_definitions = menu_definition.get("items")
        if item_definitions:
            items: list[dict[str, Any]] = []
            for item_definition in item_definitions:
                if not _is_visible(item_definition, request=request, flags=flags):
                    continue

                item = build_favoritable_page(item_definition)
                href = item["href"]
                items.append(item)
                if item["favoritable"]:
                    pages_by_url[href] = {"label": item["label"], "href": href}

            if items:
                menus.append({"label": menu_definition["label"], "children": items})
            continue

        menu = build_favoritable_page(menu_definition)
        href = menu["href"]
        menus.append(menu)
        if menu["favoritable"]:
            pages_by_url[href] = {"label": menu["label"], "href": href}

    for page_definition in EXTRA_FAVORITABLE_PAGE_DEFINITIONS:
        if not _is_visible(page_definition, request=request, flags=flags):
            continue

        page = build_favoritable_page(page_definition)
        if page["favoritable"]:
            pages_by_url.setdefault(page["href"], {"label": page["label"], "href": page["href"]})

    payload = {"menus": menus, "pages_by_url": pages_by_url}
    setattr(request, "_navbar_navigation_payload", payload)
    return payload


def get_navbar_menus(request: HttpRequest) -> list[dict[str, Any]]:
    return _build_navbar_payload(request)["menus"]


def get_favoritable_pages(request: HttpRequest) -> dict[str, dict[str, str]]:
    return _build_navbar_payload(request)["pages_by_url"]
