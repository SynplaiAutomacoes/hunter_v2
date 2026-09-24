from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.core.domain.contracts.documents import DocumentPayload, DocumentRenderRequest
from apps.core.infrastructure.excel_report_style import ExcelCell, ExcelColumn, build_hunter_excel_document
from apps.core.infrastructure.pdf.renderer import render_template_request_to_pdf
from apps.core.infrastructure.services.management_reports.period import slugify_filename_part
from apps.core.infrastructure.services.management_reports.types import ManagementReport, ReportColumnDef


def _format_display(value: object, kind: str) -> str:
    if value is None or value == "":
        return "-"
    if kind == "percent":
        amount = getattr(value, "amount", value)
        try:
            return f"{Decimal(str(amount)).quantize(Decimal('0.01'))}%".replace(".", ",")
        except Exception:
            return str(value)
    if kind.startswith("money"):
        amount = getattr(value, "amount", value)
        try:
            quantized = Decimal(str(amount)).quantize(Decimal("0.01"))
            formatted = f"{quantized:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            return f"R$ {formatted}"
        except Exception:
            return str(value)
    if kind == "date" and hasattr(value, "strftime"):
        return str(value.strftime("%d/%m/%Y"))
    return str(value)


def build_management_report_context(*, report: ManagementReport) -> dict[str, Any]:
    generated_at = timezone.localtime()
    table_rows: list[list[dict[str, str]]] = []
    for row in report.rows:
        table_rows.append(
            [
                {
                    "display": _format_display(row.get(col.key), col.kind),
                    "align": col.align,
                }
                for col in report.columns
            ]
        )
    return {
        "report": report,
        "report_title": report.title,
        "period_label": report.period_label,
        "workshop_name": report.workshop_name,
        "record_count": report.record_count,
        "columns": report.columns,
        "table_rows": table_rows,
        "rows": table_rows,
        "raw_rows": report.rows,
        "summary_cards": report.summary_cards,
        "total_label": report.total_label,
        "total_value": report.total_value,
        "total_value_display": _format_display(report.total_value, "money_sale") if report.total_value is not None else None,
        "generated_at_label": generated_at.strftime("%d/%m/%Y %H:%M"),
        "sort_options": report.sort_options,
        "selected_sort": report.selected_sort,
        "available_columns": report.available_columns,
        "selected_column_keys": report.selected_column_keys,
    }


def build_management_report_excel(*, report: ManagementReport) -> DocumentPayload:
    generated_at = timezone.localtime()
    columns = [
        ExcelColumn(header=col.label, width=col.width, kind=col.kind)
        for col in report.columns
    ]
    rows: list[list[ExcelCell]] = []
    for row in report.rows:
        cells: list[ExcelCell] = []
        for col in report.columns:
            value = row.get(col.key)
            if col.kind == "percent" and value is not None:
                # Hunter excel percent expects fraction; our values are already 0-100
                try:
                    value = Decimal(str(getattr(value, "amount", value))) / Decimal("100")
                except Exception:
                    pass
            cells.append(ExcelCell(value=value, kind=col.kind))
        rows.append(cells)

    total_cells = [ExcelCell() for _ in columns]
    if report.total_value is not None and columns:
        money_indexes = [idx for idx, col in enumerate(report.columns) if col.kind.startswith("money")]
        target = money_indexes[-1] if money_indexes else len(columns) - 1
        kind = report.columns[target].kind if target < len(report.columns) else "money_sale"
        total_cells[target] = ExcelCell(value=report.total_value, kind=kind)

    filename = f"relatorio_{slugify_filename_part(report.report_key)}_{slugify_filename_part(report.workshop_name)}_{generated_at.strftime('%Y%m%d')}.xlsx"
    return build_hunter_excel_document(
        title=f"RELATÓRIO — {report.title.upper()} ({report.period_label.upper()})",
        workshop_name=report.workshop_name,
        generated_at_label=generated_at.strftime("%d/%m/%Y às %H:%M"),
        count_label="Total de registros",
        count=report.record_count,
        sheet_title=report.title[:31],
        columns=columns,
        rows=rows,
        total_label=f"{report.total_label.upper()}   —   {report.record_count} registro(s)" if report.total_value is not None else f"TOTAL   —   {report.record_count} registro(s)",
        total_cells=total_cells,
        filename=filename,
    )


def render_management_report_pdf(*, report: ManagementReport) -> DocumentPayload:
    context = build_management_report_context(report=report)
    filename = f"relatorio_{slugify_filename_part(report.report_key)}.pdf"
    return render_template_request_to_pdf(
        DocumentRenderRequest(
            template_name="core/pdf/management_report.html",
            context=context,
            filename=filename,
        )
    )


def resolve_column_defs_for_display(columns: list[ReportColumnDef]) -> list[ReportColumnDef]:
    return columns
