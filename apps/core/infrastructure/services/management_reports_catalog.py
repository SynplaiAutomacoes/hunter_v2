from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlencode

from django.urls import NoReverseMatch, reverse

from apps.core.infrastructure.services.management_report_period import (
    ManagementReportPeriod,
    build_management_report_query_params,
)


ManagementReportCategory = Literal["performance", "estoque", "vendas", "comissoes", "cadastros"]
ManagementReportAvailability = Literal["live", "planned"]


@dataclass(frozen=True, slots=True)
class ManagementReportCatalogEntry:
    id: str
    title: str
    description: str
    category: ManagementReportCategory
    view_name: str
    availability: ManagementReportAvailability = "live"
    query_hints: dict[str, str] | None = None
    access_note: str | None = None


@dataclass(frozen=True, slots=True)
class ReportsHubCard:
    id: str
    title: str
    description: str
    availability: ManagementReportAvailability
    url: str | None
    access_note: str | None
    query_hints: dict[str, str] | None


@dataclass(frozen=True, slots=True)
class ReportsHubSection:
    category: ManagementReportCategory
    label: str
    cards: tuple[ReportsHubCard, ...]


CATEGORY_LABELS: dict[ManagementReportCategory, str] = {
    "performance": "Performance",
    "estoque": "Estoque",
    "vendas": "Vendas",
    "comissoes": "Comissões",
    "cadastros": "Cadastros",
}


MANAGEMENT_REPORT_CATALOG: tuple[ManagementReportCatalogEntry, ...] = (
    ManagementReportCatalogEntry(
        id="dashboard_performance",
        title="Painel de gestão",
        description="Indicadores de performance com exportação pelo ícone de visualização no dashboard.",
        category="performance",
        view_name="core:dashboard",
        availability="live",
        access_note="Exportação via olhinho no dashboard.",
    ),
    ManagementReportCatalogEntry(
        id="rentabilidade_acumulada",
        title="Rentabilidade acumulada",
        description="Evolução da rentabilidade no período selecionado.",
        category="performance",
        view_name="core:management_report",
        query_hints={"tipo": "rentabilidade_acumulada"},
    ),
    ManagementReportCatalogEntry(
        id="retorno_garantia",
        title="Retorno de garantia",
        description="Retornos e impacto financeiro de garantias.",
        category="performance",
        view_name="core:management_report",
        query_hints={"tipo": "retorno_garantia"},
    ),
    ManagementReportCatalogEntry(
        id="taxa_aprovacao",
        title="Taxa de aprovação",
        description="Aprovações versus orçamentos enviados.",
        category="performance",
        view_name="core:management_report",
        query_hints={"tipo": "taxa_aprovacao"},
    ),
    ManagementReportCatalogEntry(
        id="mecanicos_retrabalho",
        title="Mecânicos com retrabalho",
        description="Ranking de retrabalho por colaborador.",
        category="performance",
        view_name="core:management_report",
        query_hints={"tipo": "mecanicos_retrabalho"},
    ),
    ManagementReportCatalogEntry(
        id="stock_report_legacy",
        title="Relatório de estoque (atual)",
        description="Consulta e exportação do relatório de estoque já disponível.",
        category="estoque",
        view_name="stock:report",
        availability="live",
    ),
    ManagementReportCatalogEntry(
        id="curva_abc",
        title="Curva ABC",
        description="Classificação ABC de produtos no estoque.",
        category="estoque",
        view_name="core:management_report",
        query_hints={"tipo": "curva_abc"},
    ),
    ManagementReportCatalogEntry(
        id="estoque_minimo",
        title="Estoque mínimo",
        description="Itens abaixo ou no limite de estoque mínimo.",
        category="estoque",
        view_name="core:management_report",
        query_hints={"tipo": "estoque_minimo"},
    ),
    ManagementReportCatalogEntry(
        id="lista_contagem",
        title="Lista para contagem",
        description="Lista operacional para contagem física.",
        category="estoque",
        view_name="core:management_report",
        query_hints={"tipo": "lista_contagem"},
    ),
    ManagementReportCatalogEntry(
        id="produtos_mais_vendidos",
        title="Produtos mais vendidos",
        description="Ranking de peças mais vendidas no período.",
        category="estoque",
        view_name="core:management_report",
        query_hints={"tipo": "produtos_mais_vendidos"},
    ),
    ManagementReportCatalogEntry(
        id="produtos_geral",
        title="Produtos (visão geral)",
        description="Panorama geral de produtos e movimentação.",
        category="estoque",
        view_name="core:management_report",
        query_hints={"tipo": "produtos_geral"},
    ),
    ManagementReportCatalogEntry(
        id="total_vendas_os",
        title="Total de vendas (OS)",
        description="Total vendido em ordens de serviço no período.",
        category="vendas",
        view_name="core:management_report",
        query_hints={"tipo": "total_vendas_os"},
    ),
    ManagementReportCatalogEntry(
        id="top_clientes",
        title="Top clientes",
        description="Clientes com maior faturamento no período.",
        category="vendas",
        view_name="core:management_report",
        query_hints={"tipo": "top_clientes"},
    ),
    ManagementReportCatalogEntry(
        id="vendas_servicos",
        title="Vendas de serviços",
        description="Receita detalhada por serviços vendidos.",
        category="vendas",
        view_name="core:management_report",
        query_hints={"tipo": "vendas_servicos"},
    ),
    ManagementReportCatalogEntry(
        id="vendas_pecas",
        title="Vendas de peças",
        description="Receita detalhada por peças vendidas.",
        category="vendas",
        view_name="core:management_report",
        query_hints={"tipo": "vendas_pecas"},
    ),
    ManagementReportCatalogEntry(
        id="taxas_cartao",
        title="Taxas de cartão",
        description="Taxas e meios de pagamento no período.",
        category="vendas",
        view_name="core:management_report",
        query_hints={"tipo": "taxas_cartao"},
    ),
    ManagementReportCatalogEntry(
        id="vendas_modalidade",
        title="Vendas por modalidade",
        description="Vendas agrupadas por modalidade de atendimento.",
        category="vendas",
        view_name="core:management_report",
        query_hints={"tipo": "vendas_modalidade"},
    ),
    ManagementReportCatalogEntry(
        id="servicos_mais_vendidos",
        title="Serviços mais vendidos",
        description="Ranking de serviços no período.",
        category="vendas",
        view_name="core:management_report",
        query_hints={"tipo": "servicos_mais_vendidos"},
    ),
    ManagementReportCatalogEntry(
        id="ticket_medio",
        title="Ticket médio",
        description="Ticket médio de vendas no período.",
        category="vendas",
        view_name="core:management_report",
        query_hints={"tipo": "ticket_medio"},
    ),
    ManagementReportCatalogEntry(
        id="commission_report_legacy",
        title="Apuração de comissões (atual)",
        description="Relatório de comissões já disponível no financeiro.",
        category="comissoes",
        view_name="finance:commission_report",
        availability="live",
    ),
    ManagementReportCatalogEntry(
        id="top_mecanicos",
        title="Top mecânicos",
        description="Ranking de mecânicos por comissão ou produção.",
        category="comissoes",
        view_name="core:management_report",
        query_hints={"tipo": "top_mecanicos"},
    ),
    ManagementReportCatalogEntry(
        id="total_comissao_periodo",
        title="Total de comissão no período",
        description="Consolidado de comissões pagas e previstas.",
        category="comissoes",
        view_name="core:management_report",
        query_hints={"tipo": "total_comissao_periodo"},
    ),
    ManagementReportCatalogEntry(
        id="clientes",
        title="Relatório de clientes",
        description="Exportação analítica de clientes cadastrados.",
        category="cadastros",
        view_name="core:management_report",
        query_hints={"tipo": "clientes"},
    ),
    ManagementReportCatalogEntry(
        id="fornecedores",
        title="Relatório de fornecedores",
        description="Exportação analítica de fornecedores.",
        category="cadastros",
        view_name="core:management_report",
        query_hints={"tipo": "fornecedores"},
    ),
    ManagementReportCatalogEntry(
        id="servicos",
        title="Relatório de serviços",
        description="Catálogo de serviços com indicadores.",
        category="cadastros",
        view_name="core:management_report",
        query_hints={"tipo": "servicos"},
    ),
    ManagementReportCatalogEntry(
        id="kits",
        title="Relatório de kits",
        description="Kits cadastrados e composição.",
        category="cadastros",
        view_name="core:management_report",
        query_hints={"tipo": "kits"},
    ),
)


def get_management_report_catalog_entry(report_key: str) -> ManagementReportCatalogEntry | None:
    for entry in MANAGEMENT_REPORT_CATALOG:
        if entry.id == report_key:
            return entry
    return None


def build_reports_hub_sections() -> tuple[ReportsHubSection, ...]:
    sections: list[ReportsHubSection] = []
    for category in CATEGORY_LABELS:
        cards = tuple(
            _materialize_hub_card(entry=entry)
            for entry in MANAGEMENT_REPORT_CATALOG
            if entry.category == category
        )
        sections.append(ReportsHubSection(category=category, label=CATEGORY_LABELS[category], cards=cards))
    return tuple(sections)


def _materialize_hub_card(*, entry: ManagementReportCatalogEntry) -> ReportsHubCard:
    url: str | None = None
    if entry.availability == "live":
        url = _resolve_catalog_url(view_name=entry.view_name, query_hints=entry.query_hints)

    return ReportsHubCard(
        id=entry.id,
        title=entry.title,
        description=entry.description,
        availability=entry.availability,
        url=url,
        access_note=entry.access_note,
        query_hints=entry.query_hints,
    )


def _resolve_catalog_url(*, view_name: str, query_hints: dict[str, str] | None) -> str | None:
    try:
        base_url = reverse(view_name)
    except NoReverseMatch:
        return None
    if not query_hints:
        return base_url
    return f"{base_url}?{urlencode(query_hints)}"


def build_management_report_url(*, report_key: str, period: ManagementReportPeriod) -> str | None:
    entry = get_management_report_catalog_entry(report_key)
    if entry is None:
        return None
    try:
        base_url = reverse(entry.view_name)
    except NoReverseMatch:
        return None
    query = build_management_report_query_params(report_key=report_key, period=period)
    return f"{base_url}?{urlencode(query)}"
