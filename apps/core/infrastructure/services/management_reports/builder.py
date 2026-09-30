from __future__ import annotations

from apps.core.infrastructure.services.management_reports.cadastros import build_cadastro_report
from apps.core.infrastructure.services.management_reports.catalog import REPORT_KEYS, get_report_entry
from apps.core.infrastructure.services.management_reports.commissions import build_commission_report
from apps.core.infrastructure.services.management_reports.period import ReportPeriod
from apps.core.infrastructure.services.management_reports.performance import build_performance_report
from apps.core.infrastructure.services.management_reports.sales import build_sales_report
from apps.core.infrastructure.services.management_reports.stock_reports import build_stock_report
from apps.core.infrastructure.services.management_reports.types import ManagementReport
from apps.workshops.models.workshops import Workshop


PERFORMANCE_KEYS = frozenset(
    {
        "rentabilidade_acumulada",
        "retorno_garantia",
        "taxa_aprovacao",
        "mecanicos_retrabalho",
    }
)
STOCK_KEYS = frozenset(
    {
        "curva_abc",
        "estoque_minimo",
        "lista_contagem",
        "produtos_mais_vendidos",
        "produtos_geral",
    }
)
SALES_KEYS = frozenset(
    {
        "total_vendas_os",
        "top_clientes",
        "vendas_servicos",
        "vendas_pecas",
        "taxas_cartao",
        "vendas_modalidade",
        "servicos_mais_vendidos",
        "ticket_medio",
    }
)
COMMISSION_KEYS = frozenset({"top_mecanicos", "total_comissao_periodo"})
CADASTRO_KEYS = frozenset({"clientes", "fornecedores", "servicos_cadastro", "kits"})


def build_management_report(
    *,
    workshop: Workshop,
    period: ReportPeriod,
    report_key: str,
    sort_by: str = "perda",
    selected_columns: list[str] | None = None,
) -> ManagementReport | None:
    if report_key not in REPORT_KEYS:
        return None
    if report_key in PERFORMANCE_KEYS:
        return build_performance_report(workshop=workshop, period=period, report_key=report_key, sort_by=sort_by)
    if report_key in STOCK_KEYS:
        return build_stock_report(workshop=workshop, period=period, report_key=report_key)
    if report_key in SALES_KEYS:
        return build_sales_report(workshop=workshop, period=period, report_key=report_key)
    if report_key in COMMISSION_KEYS:
        return build_commission_report(workshop=workshop, period=period, report_key=report_key)
    if report_key in CADASTRO_KEYS:
        return build_cadastro_report(
            workshop=workshop,
            period=period,
            report_key=report_key,
            selected_columns=selected_columns,
        )
    entry = get_report_entry(report_key)
    if entry is None:
        return None
    return None
