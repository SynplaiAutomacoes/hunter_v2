from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from django.utils import timezone

from apps.core.domain.contracts.documents import DocumentPayload
from apps.core.infrastructure.excel_report_style import BadgeKey, ExcelCell, ExcelColumn, ExcelSection, build_hunter_excel_document
from apps.workshops.models.workshops import Workshop
from apps.workshops.services.workshop_reports import (
    ApprovalRateReport,
    MechanicReworkReport,
    ProfitabilityReport,
    WarrantyReturnReport,
)


def _workshop_name(workshop: Workshop) -> str:
    return workshop.pdf_name or workshop.name


def _generated_at_label() -> str:
    return timezone.localtime().strftime("%d/%m/%Y às %H:%M")


def _filename(*, slug: str, workshop: Workshop) -> str:
    workshop_fragment = re.sub(
        r"[^a-z0-9]+",
        "_",
        unicodedata.normalize("NFKD", workshop.name).encode("ascii", "ignore").decode("ascii").lower(),
    ).strip("_") or "oficina"
    stamp = timezone.localtime().strftime("%Y%m%d")
    return f"relatorio_{slug}_{workshop_fragment}_{stamp}.xlsx"


def build_mechanic_rework_excel(*, workshop: Workshop, periodo_label: str, report: MechanicReworkReport) -> DocumentPayload:
    columns = [
        ExcelColumn(header="Mecânico", width=38, kind="text"),
        ExcelColumn(header="Qtd. veículos", width=16, kind="id"),
        ExcelColumn(header="Qtd. OS garantia", width=18, kind="id"),
        ExcelColumn(header="Prejuízo acumulado", width=22, kind="money_cost"),
    ]
    sections: list[ExcelSection] = []
    for row in report.rows:
        sections.append(
            ExcelSection(
                title=f"  ▸  {row.mechanic_name.upper()}   ({row.vehicle_count} veículo(s))",
                palette="garantia",
                rows=[
                    [
                        ExcelCell(value=row.mechanic_name),
                        ExcelCell(value=row.vehicle_count, kind="id"),
                        ExcelCell(value=row.workorder_count, kind="id"),
                        ExcelCell(value=row.accumulated_loss, kind="money_cost"),
                    ]
                ],
                subtotal_label=f"   Subtotal {row.mechanic_name}  —  {row.vehicle_count} veículo(s)",
                subtotal_cells=[
                    ExcelCell(),
                    ExcelCell(value=row.vehicle_count, kind="id"),
                    ExcelCell(value=row.workorder_count, kind="id"),
                    ExcelCell(value=row.accumulated_loss, kind="money_cost"),
                ],
            )
        )
    total_cells = [
        ExcelCell(),
        ExcelCell(value=report.total_vehicles, kind="id"),
        ExcelCell(value=sum(row.workorder_count for row in report.rows), kind="id"),
        ExcelCell(value=report.total_loss, kind="money_cost"),
    ]
    return build_hunter_excel_document(
        title=f"RELATÓRIO DE RETRABALHO POR MECÂNICO — {periodo_label.upper()}",
        workshop_name=_workshop_name(workshop),
        generated_at_label=_generated_at_label(),
        count_label="Total de mecânicos",
        count=len(report.rows),
        sheet_title="Retrabalho",
        columns=columns,
        sections=sections,
        total_label=f"TOTAL GERAL   —   {len(report.rows)} mecânico(s)",
        total_cells=total_cells,
        filename=_filename(slug="retrabalho", workshop=workshop),
    )


def build_profitability_excel(*, workshop: Workshop, periodo_label: str, report: ProfitabilityReport) -> DocumentPayload:
    columns = [
        ExcelColumn(header="O.S.", width=16, kind="id"),
        ExcelColumn(header="Cliente", width=38, kind="text"),
        ExcelColumn(header="Veículo", width=30, kind="text"),
        ExcelColumn(header="Data de Entrega", width=16, kind="date"),
        ExcelColumn(header="Valor", width=18, kind="money_sale"),
        ExcelColumn(header="Rentabilidade (%)", width=18, kind="percent"),
    ]
    rows = [
        [
            ExcelCell(value=row.workorder_number),
            ExcelCell(value=row.customer_name),
            ExcelCell(value=row.vehicle_label),
            ExcelCell(value=row.delivered_at),
            ExcelCell(value=row.total_amount, kind="money_sale"),
            ExcelCell(value=row.profitability_percent, kind="percent"),
        ]
        for row in report.rows
    ]
    total_cells = [
        ExcelCell(),
        ExcelCell(),
        ExcelCell(),
        ExcelCell(),
        ExcelCell(value=report.total_amount, kind="money_sale"),
        ExcelCell(value=report.average_profitability, kind="percent"),
    ]
    return build_hunter_excel_document(
        title=f"RELATÓRIO DE RENTABILIDADE ACUMULADA — {periodo_label.upper()}",
        workshop_name=_workshop_name(workshop),
        generated_at_label=_generated_at_label(),
        count_label="Total de OS",
        count=len(report.rows),
        sheet_title="Rentabilidade",
        columns=columns,
        rows=rows,
        total_label=f"TOTAL   {len(report.rows)} OS",
        total_cells=total_cells,
        filename=_filename(slug="rentabilidade", workshop=workshop),
    )


def build_warranty_return_excel(*, workshop: Workshop, periodo_label: str, report: WarrantyReturnReport) -> DocumentPayload:
    columns = [
        ExcelColumn(header="O.S.", width=16, kind="id"),
        ExcelColumn(header="Mecânico", width=32, kind="text"),
        ExcelColumn(header="Cliente", width=32, kind="text"),
        ExcelColumn(header="Veículo", width=28, kind="text"),
        ExcelColumn(header="Data de Entrega", width=16, kind="date"),
        ExcelColumn(header="Valor total da OS", width=20, kind="money_sale"),
        ExcelColumn(header="Custo de produtos", width=20, kind="money_cost"),
        ExcelColumn(header="Custo de serviços", width=20, kind="money_cost"),
    ]
    rows = [
        [
            ExcelCell(value=row.workorder_number),
            ExcelCell(value=row.mechanic_names),
            ExcelCell(value=row.customer_name),
            ExcelCell(value=row.vehicle_label),
            ExcelCell(value=row.delivered_at),
            ExcelCell(value=row.total_amount, kind="money_sale"),
            ExcelCell(value=row.product_cost_amount, kind="money_cost"),
            ExcelCell(value=row.service_cost_amount, kind="money_cost"),
        ]
        for row in report.rows
    ]
    total_cells = [
        ExcelCell(),
        ExcelCell(),
        ExcelCell(),
        ExcelCell(),
        ExcelCell(),
        ExcelCell(value=report.total_amount, kind="money_sale"),
        ExcelCell(value=report.total_product_cost, kind="money_cost"),
        ExcelCell(value=report.total_service_cost, kind="money_cost"),
    ]
    return build_hunter_excel_document(
        title=f"RELATÓRIO DE RETORNO EM GARANTIA — {periodo_label.upper()}",
        workshop_name=_workshop_name(workshop),
        generated_at_label=_generated_at_label(),
        count_label="Total de OS",
        count=len(report.rows),
        sheet_title="Garantia",
        columns=columns,
        rows=rows,
        total_label=f"TOTAL GERAL   —   {len(report.rows)} OS",
        total_cells=total_cells,
        filename=_filename(slug="retorno_garantia", workshop=workshop),
    )


def build_approval_rate_excel(*, workshop: Workshop, periodo_label: str, report: ApprovalRateReport) -> DocumentPayload:
    columns = [
        ExcelColumn(header="Nº Orçamento", width=16, kind="id"),
        ExcelColumn(header="Cliente", width=38, kind="text"),
        ExcelColumn(header="Veículo", width=30, kind="text"),
        ExcelColumn(header="Data de Entrada", width=16, kind="date"),
        ExcelColumn(header="Status", width=22, kind="badge"),
        ExcelColumn(header="Valor", width=24, kind="money_sale"),
        ExcelColumn(header="Motivo", width=22, kind="text"),
    ]
    rows = [
        [
            ExcelCell(value=row.budget_number),
            ExcelCell(value=row.customer_name),
            ExcelCell(value=row.vehicle_label),
            ExcelCell(value=row.entry_date),
            ExcelCell(value=row.status_label, badge=_status_badge(row.status)),
            ExcelCell(value=row.total_amount, kind="money_sale"),
            ExcelCell(value=row.reason),
        ]
        for row in report.rows
    ]
    total_amount = sum((row.total_amount for row in report.rows), Decimal("0.00"))
    total_cells = [ExcelCell() for _ in columns]
    total_cells[5] = ExcelCell(value=total_amount, kind="money_sale")
    return build_hunter_excel_document(
        title=f"RELATÓRIO DE TAXA DE APROVAÇÃO — {periodo_label.upper()}",
        workshop_name=_workshop_name(workshop),
        generated_at_label=_generated_at_label(),
        count_label="Total de orçamentos",
        count=len(report.rows),
        sheet_title="Taxa de aprovacao",
        columns=columns,
        rows=rows,
        total_label=f"TOTAL   {len(report.rows)} orçamentos",
        total_cells=total_cells,
        filename=_filename(slug="taxa_aprovacao", workshop=workshop),
    )


def _status_badge(status: str) -> BadgeKey:
    if status == "approved":
        return "aprovado"
    if status == "rejected":
        return "reprovado"
    if status == "cancelled":
        return "cancelado"
    return "atencao"
