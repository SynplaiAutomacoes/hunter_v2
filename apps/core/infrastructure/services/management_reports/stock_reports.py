from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import F

from apps.catalog.models.products import Product
from apps.core.infrastructure.services.management_reports.period import ReportPeriod
from apps.core.infrastructure.services.management_reports.types import ManagementReport, ReportColumnDef
from apps.stock.models import StockProduct
from apps.workorder.models import WorkOrderItem, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def _money_amount(value: object) -> Decimal:
    amount = getattr(value, "amount", value)
    if amount is None:
        return Decimal("0.00")
    return Decimal(str(amount))


def _workshop_name(workshop: Workshop) -> str:
    return workshop.pdf_name or workshop.name or "-"


def build_estoque_minimo(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    qs = (
        StockProduct.objects.filter(workshop=workshop, current_quantity__lt=F("minimum_quantity"))
        .select_related("product", "product__group")
        .order_by("product__name")
    )
    rows = [
        {
            "codigo": item.product.code if item.product_id else "-",
            "produto": item.product.name if item.product_id else "-",
            "grupo": str(item.product.group) if item.product_id and item.product.group_id else "-",
            "qtd_atual": item.current_quantity,
            "estoque_minimo": item.minimum_quantity,
            "faltante": max(item.minimum_quantity - item.current_quantity, 0),
            "localizacao": item.product.location if item.product_id else "-",
        }
        for item in qs
    ]
    columns = [
        ReportColumnDef("codigo", "Código", kind="id", width=14),
        ReportColumnDef("produto", "Produto", width=36),
        ReportColumnDef("grupo", "Grupo", width=20),
        ReportColumnDef("qtd_atual", "Qtd. atual", align="right", width=12),
        ReportColumnDef("estoque_minimo", "Estoque mínimo", align="right", width=14),
        ReportColumnDef("faltante", "Faltante", align="right", width=12),
        ReportColumnDef("localizacao", "Localização", width=18),
    ]
    return ManagementReport(
        report_key="estoque_minimo",
        title="Estoque Mínimo",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
    )


def build_lista_contagem(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    qs = (
        StockProduct.objects.filter(workshop=workshop)
        .select_related("product", "product__group")
        .order_by("product__location", "product__name")
    )
    rows = [
        {
            "codigo": item.product.code if item.product_id else "-",
            "produto": item.product.name if item.product_id else "-",
            "localizacao": item.product.location if item.product_id else "-",
            "qtd_sistema": item.current_quantity,
            "contagem_fisica": "",
        }
        for item in qs
    ]
    columns = [
        ReportColumnDef("codigo", "Código", kind="id", width=14),
        ReportColumnDef("produto", "Produto", width=40),
        ReportColumnDef("localizacao", "Localização", width=18),
        ReportColumnDef("qtd_sistema", "Qtd. sistema", align="right", width=14),
        ReportColumnDef("contagem_fisica", "Contagem física", align="right", width=16),
    ]
    return ManagementReport(
        report_key="lista_contagem",
        title="Lista para contagem de inventário",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
    )


def build_produtos_geral(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    qs = (
        Product.objects.filter(workshop=workshop)
        .select_related("group", "stock_products")
        .order_by("name")
    )
    rows: list[dict[str, Any]] = []
    for product in qs:
        stock = getattr(product, "stock_products", None)
        rows.append(
            {
                "codigo": product.code,
                "nome": product.name,
                "descricao": product.description or "-",
                "grupo": str(product.group) if product.group_id else "-",
                "marca": product.brand or "-",
                "modelo": product.model or "-",
                "unidade": product.unit,
                "valor_venda": _money_amount(product.selling_price),
                "valor_custo": _money_amount(product.cost_price),
                "estoque": stock.current_quantity if stock else 0,
                "estoque_minimo": stock.minimum_quantity if stock else 0,
                "localizacao": product.location or "-",
                "sku": product.sku or "-",
                "ncm": product.ncm or "-",
                "cadastrado_em": product.criado_em.date() if product.criado_em else None,
                "ativo": "Sim" if product.is_active else "Não",
            }
        )
    columns = [
        ReportColumnDef("codigo", "Código", kind="id", width=12),
        ReportColumnDef("nome", "Nome", width=28),
        ReportColumnDef("descricao", "Descrição", width=32),
        ReportColumnDef("grupo", "Grupo", width=16),
        ReportColumnDef("marca", "Marca", width=14),
        ReportColumnDef("modelo", "Modelo", width=14),
        ReportColumnDef("unidade", "Unidade", width=10),
        ReportColumnDef("valor_venda", "Valor de venda", kind="money_sale", align="right", width=14),
        ReportColumnDef("valor_custo", "Valor de custo", kind="money_cost", align="right", width=14),
        ReportColumnDef("estoque", "Estoque", align="right", width=10),
        ReportColumnDef("estoque_minimo", "Estoque mínimo", align="right", width=12),
        ReportColumnDef("localizacao", "Localização", width=14),
        ReportColumnDef("sku", "SKU", width=12),
        ReportColumnDef("ncm", "NCM", width=12),
        ReportColumnDef("cadastrado_em", "Cadastrado em", kind="date", width=14),
        ReportColumnDef("ativo", "Ativo", width=10),
    ]
    return ManagementReport(
        report_key="produtos_geral",
        title="Relatório geral de produtos",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
    )


def build_produtos_mais_vendidos(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    raw_items = list(
        WorkOrderItem.objects.filter(
            workshop=workshop,
            product_id__isnull=False,
            workorder__status=WorkOrderStatus.APPROVED,
            workorder__budget_type="sale",
            workorder__delivered_at__month=period.month,
            workorder__delivered_at__year=period.year,
        ).select_related("product")
    )
    aggregates: dict[int, dict[str, Any]] = {}
    for item in raw_items:
        if not item.product_id:
            continue
        bucket = aggregates.setdefault(
            item.product_id,
            {
                "codigo": item.product.code,
                "produto": item.product.name,
                "quantidade": 0,
                "faturamento": Decimal("0.00"),
            },
        )
        qty = int(item.quantity or 0)
        bucket["quantidade"] += qty
        bucket["faturamento"] += _money_amount(item.product_selling_price) * qty
    rows = sorted(aggregates.values(), key=lambda r: (int(r["quantidade"]), Decimal(str(r["faturamento"]))), reverse=True)
    columns = [
        ReportColumnDef("codigo", "Código", kind="id", width=14),
        ReportColumnDef("produto", "Produto", width=40),
        ReportColumnDef("quantidade", "Quantidade", align="right", width=14),
        ReportColumnDef("faturamento", "Faturamento", kind="money_sale", align="right", width=16),
    ]
    return ManagementReport(
        report_key="produtos_mais_vendidos",
        title="Produtos mais vendidos",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
        total_value=sum((Decimal(str(r["faturamento"])) for r in rows), Decimal("0.00")),
        total_label="Faturamento total",
    )


def build_curva_abc(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    sales_report = build_produtos_mais_vendidos(workshop=workshop, period=period)
    rows = list(sales_report.rows)
    total = sum((Decimal(str(r["faturamento"])) for r in rows), Decimal("0.00"))
    cumulative = Decimal("0.00")
    abc_rows: list[dict[str, Any]] = []
    for row in rows:
        fat = Decimal(str(row["faturamento"]))
        share = (fat / total * Decimal("100")) if total else Decimal("0.00")
        cumulative += share
        if cumulative <= Decimal("80"):
            classe = "A"
        elif cumulative <= Decimal("95"):
            classe = "B"
        else:
            classe = "C"
        abc_rows.append(
            {
                **row,
                "participacao": share,
                "acumulado": cumulative,
                "classe": classe,
            }
        )
    columns = [
        ReportColumnDef("classe", "Classe", width=10),
        ReportColumnDef("codigo", "Código", kind="id", width=14),
        ReportColumnDef("produto", "Produto", width=36),
        ReportColumnDef("quantidade", "Quantidade", align="right", width=12),
        ReportColumnDef("faturamento", "Faturamento", kind="money_sale", align="right", width=16),
        ReportColumnDef("participacao", "Participação %", kind="percent", align="right", width=14),
        ReportColumnDef("acumulado", "Acumulado %", kind="percent", align="right", width=14),
    ]
    return ManagementReport(
        report_key="curva_abc",
        title="Curva ABC do estoque",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=abc_rows,
        total_value=total,
        total_label="Faturamento total",
    )


def build_stock_report(*, workshop: Workshop, period: ReportPeriod, report_key: str) -> ManagementReport | None:
    builders = {
        "curva_abc": build_curva_abc,
        "estoque_minimo": build_estoque_minimo,
        "lista_contagem": build_lista_contagem,
        "produtos_mais_vendidos": build_produtos_mais_vendidos,
        "produtos_geral": build_produtos_geral,
    }
    builder = builders.get(report_key)
    if builder is None:
        return None
    return builder(workshop=workshop, period=period)
