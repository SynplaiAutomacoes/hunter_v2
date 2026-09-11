from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from django.db.models import Prefetch
from django.utils import timezone

from apps.core.domain.contracts.documents import DocumentPayload, DocumentRenderRequest
from apps.core.infrastructure.excel_report_style import ExcelCell, ExcelColumn, build_hunter_excel_document
from apps.core.infrastructure.pdf.renderer import render_template_request_to_pdf
from apps.core.infrastructure.services.webmania.emission import NfseEmissionError, calculate_nfse_service_total
from apps.core.infrastructure.services.webmania.nfe_emission import compute_product_discount_for_nfe
from apps.finance.models.finance import (
    NfeItem,
    NfeRequest,
    NfeRequestStatus,
    NfseItem,
    NfseRequest,
    NfseRequestStatus,
    StandaloneNfeLine,
    StandaloneNfseLine,
)
from apps.finance.services.pricing import build_slider_allocation_for_workorder
from apps.workshops.models.workshops import Workshop


logger = logging.getLogger(__name__)

NOTE_TYPE = Literal["nfe", "nfse"]
REPORT_STATUSES = frozenset({NfeRequestStatus.APPROVED, NfeRequestStatus.CANCELED})
NFSE_REPORT_STATUSES = frozenset({NfseRequestStatus.APPROVED, NfseRequestStatus.CANCELED})

_QUANTIZE = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class IssuedDocumentReportRow:
    number: str
    customer_name: str
    workorder_label: str
    issued_at: datetime
    amount: Decimal | None
    status: str
    status_label: str
    include_in_total: bool


@dataclass(frozen=True, slots=True)
class IssuedDocumentsReport:
    workshop: Workshop
    note_type: NOTE_TYPE
    note_type_label: str
    start_date: date | None
    end_date: date | None
    period_label: str
    rows: list[IssuedDocumentReportRow]
    total_amount: Decimal
    generated_at: datetime

    @property
    def record_count(self) -> int:
        return len(self.rows)

    @property
    def total_amount_display(self) -> str:
        return _format_brl(self.total_amount)


def build_issued_documents_report(
    *,
    workshop: Workshop,
    note_type: NOTE_TYPE,
    start_date: date | None = None,
    end_date: date | None = None,
) -> IssuedDocumentsReport:
    if note_type == "nfe":
        rows = _build_nfe_rows(workshop=workshop, start_date=start_date, end_date=end_date)
        note_type_label = "Nota Fiscal de Produto (NF-e)"
    else:
        rows = _build_nfse_rows(workshop=workshop, start_date=start_date, end_date=end_date)
        note_type_label = "Nota Fiscal de Serviço (NFS-e)"

    total_amount = sum((row.amount for row in rows if row.include_in_total and row.amount is not None), Decimal("0.00")).quantize(_QUANTIZE)
    return IssuedDocumentsReport(
        workshop=workshop,
        note_type=note_type,
        note_type_label=note_type_label,
        start_date=start_date,
        end_date=end_date,
        period_label=_build_period_label(start_date=start_date, end_date=end_date),
        rows=rows,
        total_amount=total_amount,
        generated_at=timezone.localtime(),
    )


def build_issued_documents_report_context(*, report: IssuedDocumentsReport) -> dict[str, object]:
    return {
        "workshop": report.workshop,
        "note_type": report.note_type,
        "note_type_label": report.note_type_label,
        "period_label": report.period_label,
        "report_title": f"Relatório de {report.note_type_label}",
        "record_count": report.record_count,
        "total_amount": report.total_amount,
        "total_amount_display": report.total_amount_display,
        "generated_at_label": timezone.localtime(report.generated_at).strftime("%d/%m/%Y %H:%M"),
        "rows": [
            {
                "number": row.number,
                "customer_name": row.customer_name,
                "workorder_label": row.workorder_label,
                "issued_at": row.issued_at,
                "issued_at_label": timezone.localtime(row.issued_at).strftime("%d/%m/%Y %H:%M"),
                "amount": row.amount,
                "amount_display": _format_brl(row.amount) if row.amount is not None else "-",
                "status": row.status,
                "status_label": row.status_label,
                "include_in_total": row.include_in_total,
            }
            for row in report.rows
        ],
    }


def render_issued_documents_report_pdf(*, report: IssuedDocumentsReport) -> DocumentPayload:
    context = build_issued_documents_report_context(report=report)
    filename = _build_filename(report=report, extension="pdf")
    return render_template_request_to_pdf(
        DocumentRenderRequest(
            template_name="finance/issued_documents/pdf/report.html",
            context=context,
            filename=filename,
        )
    )


def build_issued_documents_report_excel(*, report: IssuedDocumentsReport) -> DocumentPayload:
    context = build_issued_documents_report_context(report=report)
    columns = [
        ExcelColumn(header="Nº da Nota", width=16, kind="text"),
        ExcelColumn(header="Nome Cliente", width=36, kind="text"),
        ExcelColumn(header="OS", width=14, kind="text"),
        ExcelColumn(header="Data emissão", width=18, kind="date"),
        ExcelColumn(header="Valor da Nota", width=16, kind="money_sale"),
        ExcelColumn(header="Status", width=16, kind="text"),
    ]
    excel_rows: list[list[ExcelCell]] = []
    for row in report.rows:
        excel_rows.append(
            [
                ExcelCell(value=row.number),
                ExcelCell(value=row.customer_name),
                ExcelCell(value=row.workorder_label),
                ExcelCell(value=timezone.localtime(row.issued_at).date(), kind="date"),
                ExcelCell(value=row.amount if row.amount is not None else None, kind="money_sale"),
                ExcelCell(value=row.status_label),
            ]
        )

    return build_hunter_excel_document(
        title=str(context["report_title"]),
        workshop_name=report.workshop.name,
        generated_at_label=str(context["generated_at_label"]),
        count_label="Notas",
        count=report.record_count,
        sheet_title="Notas",
        columns=columns,
        rows=excel_rows,
        total_label=f"Valor total ({report.period_label})",
        total_cells=[
            ExcelCell(),
            ExcelCell(),
            ExcelCell(),
            ExcelCell(),
            ExcelCell(value=report.total_amount, kind="money_sale"),
            ExcelCell(),
        ],
        filename=_build_filename(report=report, extension="xlsx"),
    )


def resolve_nfe_note_amount(nfe_request: NfeRequest) -> Decimal | None:
    try:
        if nfe_request.standalone_lines.exists():
            total = sum((Decimal(str(line.total_value)) for line in nfe_request.standalone_lines.all()), Decimal("0.00"))
            return _quantize_money(total)

        workorder = nfe_request.workorder
        if workorder is None:
            return None

        allocation = build_slider_allocation_for_workorder(
            workorder=workorder,
            persisted_slider=getattr(nfe_request, "pricing_slider", None),
        )
        product_discount = compute_product_discount_for_nfe(
            workorder=workorder,
            products_target=allocation.products_target,
            services_target=allocation.services_target,
            discount_type_override=str(getattr(nfe_request, "discount_type_override", "") or ""),
        )
        return _quantize_money(allocation.products_target - product_discount)
    except Exception:
        logger.exception("issued_documents_report_nfe_amount_failed", extra={"nfe_request_id": getattr(nfe_request, "pk", None)})
        return None


def resolve_nfse_note_amount(nfse_request: NfseRequest) -> Decimal | None:
    try:
        return _quantize_money(Decimal(calculate_nfse_service_total(nfse_request)))
    except (NfseEmissionError, Exception):
        logger.exception("issued_documents_report_nfse_amount_failed", extra={"nfse_request_id": getattr(nfse_request, "pk", None)})
        return None


def _build_nfe_rows(*, workshop: Workshop, start_date: date | None, end_date: date | None) -> list[IssuedDocumentReportRow]:
    qs = (
        NfeRequest.objects.filter(workshop=workshop, status__in=REPORT_STATUSES)
        .select_related("workorder", "workorder__budget", "workorder__budget__customer")
        .prefetch_related(
            Prefetch("items", queryset=NfeItem.objects.order_by("-id"), to_attr="prefetched_items"),
            Prefetch("standalone_lines", queryset=StandaloneNfeLine.objects.order_by("sort_order", "id")),
        )
        .order_by("-criado_em", "-pk")
    )
    if start_date and end_date:
        qs = qs.filter(criado_em__date__range=(start_date, end_date))

    rows: list[IssuedDocumentReportRow] = []
    for request_obj in qs:
        amount = resolve_nfe_note_amount(request_obj)
        include_in_total = request_obj.status == NfeRequestStatus.APPROVED and amount is not None
        rows.append(
            IssuedDocumentReportRow(
                number=request_obj.number_display_listing,
                customer_name=request_obj.customer_name,
                workorder_label=_workorder_label(request_obj),
                issued_at=request_obj.criado_em,
                amount=amount,
                status=str(request_obj.status),
                status_label=str(NfeRequestStatus(request_obj.status).label),
                include_in_total=include_in_total,
            )
        )
    return rows


def _build_nfse_rows(*, workshop: Workshop, start_date: date | None, end_date: date | None) -> list[IssuedDocumentReportRow]:
    qs = (
        NfseRequest.objects.filter(workshop=workshop, status__in=NFSE_REPORT_STATUSES)
        .select_related("workorder", "workorder__budget", "workorder__budget__customer")
        .prefetch_related(
            Prefetch("items", queryset=NfseItem.objects.order_by("-id"), to_attr="prefetched_items"),
            Prefetch("standalone_lines", queryset=StandaloneNfseLine.objects.order_by("sort_order", "id")),
        )
        .order_by("-criado_em", "-pk")
    )
    if start_date and end_date:
        qs = qs.filter(criado_em__date__range=(start_date, end_date))

    rows: list[IssuedDocumentReportRow] = []
    for request_obj in qs:
        amount = resolve_nfse_note_amount(request_obj)
        include_in_total = request_obj.status == NfseRequestStatus.APPROVED and amount is not None
        rows.append(
            IssuedDocumentReportRow(
                number=_nfse_number_display(request_obj),
                customer_name=request_obj.customer_name,
                workorder_label=_workorder_label(request_obj),
                issued_at=request_obj.criado_em,
                amount=amount,
                status=str(request_obj.status),
                status_label=str(NfseRequestStatus(request_obj.status).label),
                include_in_total=include_in_total,
            )
        )
    return rows


def _nfse_number_display(request_obj: NfseRequest) -> str:
    if request_obj.status == NfseRequestStatus.REPROVED:
        return "-"
    prefetched_items = getattr(request_obj, "prefetched_items", None)
    latest_item = prefetched_items[0] if prefetched_items else None
    note_number = str(getattr(latest_item, "number", "") or "").strip() if latest_item is not None else ""
    return note_number or request_obj.rps_number_display


def _workorder_label(request_obj: NfeRequest | NfseRequest) -> str:
    if request_obj.workorder_id is None:
        return "Avulsa"
    workorder = request_obj.workorder
    return f"#{workorder.get_id}"


def _build_period_label(*, start_date: date | None, end_date: date | None) -> str:
    if start_date and end_date:
        return f"{start_date.strftime('%d/%m/%Y')} até {end_date.strftime('%d/%m/%Y')}"
    return "Todo o período"


def _build_filename(*, report: IssuedDocumentsReport, extension: str) -> str:
    workshop_fragment = _normalize_filename_fragment(report.workshop.name)
    type_fragment = report.note_type
    if report.start_date and report.end_date:
        period_fragment = f"{report.start_date.isoformat()}_{report.end_date.isoformat()}"
    else:
        period_fragment = "todo_periodo"
    return f"relatorio_{type_fragment}_{workshop_fragment}_{period_fragment}.{extension}"


def _normalize_filename_fragment(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_value).strip("-._")
    return cleaned or "oficina"


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(_QUANTIZE, rounding=ROUND_HALF_UP)


def _format_brl(amount: Decimal) -> str:
    quantized = _quantize_money(amount)
    integer_part, decimal_part = f"{quantized:.2f}".split(".")
    grouped_integer = f"{int(integer_part):,}".replace(",", ".")
    return f"R$ {grouped_integer},{decimal_part}"
