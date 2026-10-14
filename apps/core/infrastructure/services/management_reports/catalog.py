from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReportCatalogEntry:
    key: str
    title: str
    description: str
    category: str
    icon: str = "assessment"


REPORT_CATALOG: tuple[ReportCatalogEntry, ...] = (
    # Performance
    ReportCatalogEntry(
        key="rentabilidade_acumulada",
        title="Rentabilidade Acumulada",
        description="Lista OS do período com a rentabilidade de cada uma.",
        category="Performance",
        icon="trending_up",
    ),
    ReportCatalogEntry(
        key="retorno_garantia",
        title="Retorno em Garantia",
        description="OS de garantia/cortesia com mecânico, valor e custo.",
        category="Performance",
        icon="replay",
    ),
    ReportCatalogEntry(
        key="taxa_aprovacao",
        title="Taxa de Aprovação",
        description="Orçamentos por status (aprovado, reprovado, cancelado) com motivo.",
        category="Performance",
        icon="verified",
    ),
    ReportCatalogEntry(
        key="mecanicos_retrabalho",
        title="Mecânicos que mais geram retrabalhos",
        description="Ranking de O.S. de garantia/cortesia por falha de mão de obra ou falha de mão de obra e peça.",
        category="Performance",
        icon="engineering",
    ),
    # Estoque
    ReportCatalogEntry(
        key="curva_abc",
        title="Curva ABC do estoque",
        description="Classificação A/B/C dos produtos por faturamento no período.",
        category="Estoque",
        icon="stacked_bar_chart",
    ),
    ReportCatalogEntry(
        key="estoque_minimo",
        title="Estoque Mínimo",
        description="Itens abaixo do estoque mínimo cadastrado.",
        category="Estoque",
        icon="warning",
    ),
    ReportCatalogEntry(
        key="lista_contagem",
        title="Lista para contagem de inventário",
        description="Lista operacional para contagem física do estoque.",
        category="Estoque",
        icon="checklist",
    ),
    ReportCatalogEntry(
        key="produtos_mais_vendidos",
        title="Produtos mais vendidos",
        description="Peças com maior volume de venda no período.",
        category="Estoque",
        icon="local_offer",
    ),
    ReportCatalogEntry(
        key="produtos_geral",
        title="Relatório geral de produtos",
        description="Cadastro completo: nome, descrição, venda, custo, estoque e datas.",
        category="Estoque",
        icon="inventory_2",
    ),
    # Vendas
    ReportCatalogEntry(
        key="total_vendas_os",
        title="Total vendas OS",
        description="Vendas do período com valores bruto e líquido por OS.",
        category="Vendas",
        icon="point_of_sale",
    ),
    ReportCatalogEntry(
        key="top_clientes",
        title="Top Clientes",
        description="Clientes com maior volume acumulado de vendas.",
        category="Vendas",
        icon="groups",
    ),
    ReportCatalogEntry(
        key="vendas_servicos",
        title="Total vendas de serviços",
        description="Vendas de serviços no período (bruto e líquido).",
        category="Vendas",
        icon="build",
    ),
    ReportCatalogEntry(
        key="vendas_pecas",
        title="Total vendas de peças",
        description="Vendas de peças no período (bruto e líquido).",
        category="Vendas",
        icon="settings",
    ),
    ReportCatalogEntry(
        key="taxas_cartao",
        title="Total de taxas de cartão",
        description="Taxas de maquininha pagas no período e percentuais sobre vendas.",
        category="Vendas",
        icon="credit_card",
    ),
    ReportCatalogEntry(
        key="vendas_modalidade",
        title="Vendas por modalidade",
        description="Vendas agrupadas por forma de pagamento (pix, cartão, boleto…).",
        category="Vendas",
        icon="payments",
    ),
    ReportCatalogEntry(
        key="servicos_mais_vendidos",
        title="Serviços mais vendidos",
        description="Serviços ordenados por rentabilidade/faturamento.",
        category="Vendas",
        icon="handyman",
    ),
    ReportCatalogEntry(
        key="ticket_medio",
        title="Ticket médio",
        description="Detalhamento das OS que compõem o ticket médio do período.",
        category="Vendas",
        icon="confirmation_number",
    ),
    # Comissões
    ReportCatalogEntry(
        key="top_mecanicos",
        title="Top mecânicos do mês",
        description="Mecânicos ordenados por produção/comissão no período.",
        category="Comissões",
        icon="emoji_events",
    ),
    ReportCatalogEntry(
        key="total_comissao_periodo",
        title="Total de comissão por período",
        description="Comissões com valor OS, líquido, mecânico e percentual.",
        category="Comissões",
        icon="paid",
    ),
    # Cadastros
    ReportCatalogEntry(
        key="clientes",
        title="Clientes",
        description="Exportação de clientes com colunas opcionais à escolha.",
        category="Cadastros",
        icon="person",
    ),
    ReportCatalogEntry(
        key="fornecedores",
        title="Fornecedores",
        description="Listagem de fornecedores da oficina.",
        category="Cadastros",
        icon="local_shipping",
    ),
    ReportCatalogEntry(
        key="servicos_cadastro",
        title="Serviços",
        description="Cadastro de serviços da oficina.",
        category="Cadastros",
        icon="miscellaneous_services",
    ),
    ReportCatalogEntry(
        key="kits",
        title="Kits",
        description="Cadastro de kits da oficina.",
        category="Cadastros",
        icon="widgets",
    ),
)

CATEGORY_ORDER: tuple[str, ...] = ("Performance", "Estoque", "Vendas", "Comissões", "Cadastros")

REPORT_KEYS = frozenset(entry.key for entry in REPORT_CATALOG)


def get_report_entry(key: str) -> ReportCatalogEntry | None:
    for entry in REPORT_CATALOG:
        if entry.key == key:
            return entry
    return None


def group_catalog_by_category() -> list[dict[str, object]]:
    grouped: list[dict[str, object]] = []
    for category in CATEGORY_ORDER:
        entries = [entry for entry in REPORT_CATALOG if entry.category == category]
        if entries:
            grouped.append({"category": category, "entries": entries})
    return grouped
