from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.core.domain.contracts.documents import DocumentPayload
from apps.core.infrastructure.excel_report_style import BadgeKey, ExcelCell, ExcelColumn, build_hunter_excel_document
from apps.core.infrastructure.services.dashboard_query_service import resolve_indicator_row_amount
from apps.core.workorder_numbers import resolve_budget_workorder_number, resolve_workorder_number
from apps.workshops.models.workshops import Workshop


def build_dashboard_financial_report_excel(*, context: dict[str, Any]) -> DocumentPayload:
    workshop = context.get("workshop")
    workshop_name = "-"
    if isinstance(workshop, Workshop):
        workshop_name = workshop.pdf_name or workshop.name
    indicator = str(context.get("indicator") or "relatorio")
    report_title = str(context.get("report_title") or "Relatorio gerencial")
    periodo_label = str(context.get("periodo_label") or "-")
    generated_at = timezone.localtime()
    generated_at_label = generated_at.strftime("%d/%m/%Y às %H:%M")
    record_count = int(context.get("record_count") or 0)
    is_budget_report = bool(context.get("is_budget_report"))
    value_column_label = str(context.get("value_column_label") or "Valor")

    if is_budget_report:
        columns, rows, total_cells = _build_budget_sheet(context=context, value_column_label=value_column_label)
        count_label = "Total de orçamentos"
    else:
        columns, rows, total_cells = _build_workorder_sheet(context=context, value_column_label=value_column_label)
        count_label = "Total de OS"

    filename = _build_filename(workshop_name=str(workshop_name), indicator=indicator, stamp=generated_at.strftime("%Y%m%d"))
    return build_hunter_excel_document(
        title=f"RELATÓRIO — {report_title.upper()} ({periodo_label.upper()})",
        workshop_name=str(workshop_name),
        generated_at_label=generated_at_label,
        count_label=count_label,
        count=record_count,
        sheet_title=report_title[:31],
        columns=columns,
        rows=rows,
        total_label=f"TOTAL GERAL   —   {record_count} registro(s)",
        total_cells=total_cells,
        filename=filename,
    )


def _build_budget_sheet(*, context: dict[str, Any], value_column_label: str) -> tuple[list[ExcelColumn], list[list[ExcelCell]], list[ExcelCell]]:
    include_reason = str(context.get("indicator") or "") == "reprovados"
    columns = [
        ExcelColumn(header="Nº Orçamento", width=16, kind="id"),
        ExcelColumn(header="Cliente", width=38, kind="text"),
        ExcelColumn(header="Data", width=16, kind="date"),
        ExcelColumn(header="Veículo", width=30, kind="text"),
    ]
    if include_reason:
        columns.append(ExcelColumn(header="Motivo", width=28, kind="text"))
    columns.append(ExcelColumn(header=value_column_label, width=18, kind="money_sale"))

    rows: list[list[ExcelCell]] = []
    total = Decimal("0.00")
    indicator = str(context.get("indicator") or "")
    for item in context.get("report_rows") or []:
        amount = resolve_indicator_row_amount(item=item, indicator=indicator, is_budget_report=True)
        total += amount
        row = [
            ExcelCell(value=resolve_budget_workorder_number(item)),
            ExcelCell(value=str(getattr(item, "customer", None) or "-")),
            ExcelCell(value=getattr(item, "entry_date", None)),
            ExcelCell(value=str(getattr(item, "vehicle", None) or "-")),
        ]
        if include_reason:
            row.append(ExcelCell(value=getattr(item, "rejection_reason", None) or "-"))
        row.append(ExcelCell(value=amount, kind="money_sale"))
        rows.append(row)

    total_cells = [ExcelCell() for _ in columns]
    total_cells[-1] = ExcelCell(value=total, kind="money_sale")
    return columns, rows, total_cells


def _build_workorder_sheet(*, context: dict[str, Any], value_column_label: str) -> tuple[list[ExcelColumn], list[list[ExcelCell]], list[ExcelCell]]:
    columns = [
        ExcelColumn(header="O.S.", width=16, kind="id"),
        ExcelColumn(header="Cliente", width=38, kind="text"),
        ExcelColumn(header="Veículo", width=30, kind="text"),
        ExcelColumn(header="Data", width=16, kind="date"),
        ExcelColumn(header="Tipo", width=14, kind="badge"),
        ExcelColumn(header="Vínculo", width=23, kind="text"),
        ExcelColumn(header=value_column_label, width=18, kind="money_sale"),
    ]
    rows: list[list[ExcelCell]] = []
    total = Decimal("0.00")
    indicator = str(context.get("indicator") or "")
    daily_sales_groups = context.get("daily_sales_groups") or []
    if daily_sales_groups:
        for group_index, group in enumerate(daily_sales_groups):
            row_fill = "white" if group_index % 2 == 0 else "zebra"
            for item in group.items:
                amount = resolve_indicator_row_amount(item=item, indicator=indicator, is_budget_report=False)
                total += amount
                rows.append(
                    _workorder_row(
                        item=item,
                        amount=amount,
                        link_label=f"Venda em {group.sales_date.strftime('%d/%m/%Y')}",
                        row_fill=row_fill,
                    )
                )
            rows.append(
                [
                    ExcelCell(row_fill=row_fill),
                    ExcelCell(value="TOTAL DO DIA"),
                    ExcelCell(),
                    ExcelCell(value=group.sales_date),
                    ExcelCell(),
                    ExcelCell(),
                    ExcelCell(value=group.total, kind="money_sale"),
                ]
            )
        total_cells = [ExcelCell() for _ in columns]
        total_cells[-1] = ExcelCell(value=total, kind="money_sale")
        return columns, rows, total_cells

    groups = context.get("workorder_groups") or []
    if groups:
        for group in groups:
            total += getattr(group, "group_total", Decimal("0.00")) or Decimal("0.00")
            rows.append(_workorder_row(item=group.primary_item, amount=group.primary_amount, link_label="Principal"))
            for child in group.child_items:
                child_amount = resolve_indicator_row_amount(item=child, indicator=indicator, is_budget_report=False)
                rows.append(_workorder_row(item=child, amount=child_amount, link_label="Filha"))
    else:
        for item in context.get("items") or []:
            amount = resolve_indicator_row_amount(item=item, indicator=indicator, is_budget_report=False)
            total += amount
            rows.append(_workorder_row(item=item, amount=amount, link_label="-"))

    total_cells = [ExcelCell() for _ in columns]
    total_cells[-1] = ExcelCell(value=total, kind="money_sale")
    return columns, rows, total_cells


def _workorder_row(*, item: Any, amount: Decimal, link_label: str, row_fill: str | None = None) -> list[ExcelCell]:
    budget = getattr(item, "budget", None)
    budget_type = str(getattr(item, "budget_type", "") or "")
    row_date = getattr(item, "delivered_at", None) or getattr(item, "criado_em", None)
    return [
        ExcelCell(value=resolve_workorder_number(item), row_fill=row_fill),
        ExcelCell(value=str(getattr(budget, "customer", None) or "-")),
        ExcelCell(value=str(getattr(budget, "vehicle", None) or "-")),
        ExcelCell(value=row_date),
        ExcelCell(value=_budget_type_label(budget_type), badge=_budget_type_badge(budget_type)),
        ExcelCell(value=link_label),
        ExcelCell(value=amount, kind="money_sale"),
    ]


def _budget_type_label(budget_type: str) -> str:
    mapping = {"sale": "Venda", "direct_sale": "Venda Direta", "warranty": "Garantia", "courtesy": "Cortesia"}
    return mapping.get(budget_type, budget_type or "-")


def _budget_type_badge(budget_type: str) -> BadgeKey:
    mapping = {"sale": "venda", "direct_sale": "venda", "warranty": "garantia", "courtesy": "cortesia"}
    return mapping.get(budget_type, "venda")


def _build_filename(*, workshop_name: str, indicator: str, stamp: str) -> str:
    workshop_fragment = _normalize_filename_fragment(workshop_name)
    indicator_fragment = _normalize_filename_fragment(indicator)
    return f"relatorio_{indicator_fragment}_{workshop_fragment}_{stamp}.xlsx"


def _normalize_filename_fragment(value: str) -> str:
    normalized_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized_value = normalized_value.lower().strip()
    normalized_value = re.sub(r"[^a-z0-9]+", "_", normalized_value)
    normalized_value = normalized_value.strip("_")
    return normalized_value or "relatorio"
