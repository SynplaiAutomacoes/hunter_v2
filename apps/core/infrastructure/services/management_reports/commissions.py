from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Q

from apps.collaborators.models import CollaboratorCommissionEntry
from apps.core.infrastructure.services.management_reports.period import ReportPeriod
from apps.core.infrastructure.services.management_reports.types import ManagementReport, ReportColumnDef
from apps.core.workorder_numbers import resolve_workorder_number
from apps.workorder.models import WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def _money_amount(value: object) -> Decimal:
    amount = getattr(value, "amount", value)
    if amount is None:
        return Decimal("0.00")
    return Decimal(str(amount))


def _workshop_name(workshop: Workshop) -> str:
    return workshop.pdf_name or workshop.name or "-"


def _visible_commission_filter() -> Q:
    return (
        Q(status=CollaboratorCommissionEntry.Status.PAID)
        | Q(origin=CollaboratorCommissionEntry.Origin.MANUAL)
        | Q(
            status=CollaboratorCommissionEntry.Status.FORECAST,
            workorder__status=WorkOrderStatus.APPROVED,
            workorder__budget_type="sale",
        )
    )


def _commission_queryset(*, workshop: Workshop, period: ReportPeriod):
    qs = (
        CollaboratorCommissionEntry.objects.filter(workshop=workshop)
        .filter(_visible_commission_filter())
        .select_related("collaborator", "workorder", "workorder__budget", "workorder__budget__customer")
    )
    if period.start_date or period.end_date:
        if period.start_date:
            qs = qs.filter(criado_em__date__gte=period.start_date)
        if period.end_date:
            qs = qs.filter(criado_em__date__lte=period.end_date)
    else:
        qs = qs.filter(criado_em__month=period.month, criado_em__year=period.year)
    return qs.order_by("-criado_em", "-id")


def build_top_mecanicos(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    qs = _commission_queryset(workshop=workshop, period=period)
    aggregates: dict[int, dict[str, Any]] = {}
    for entry in qs:
        if entry.collaborator_id is None:
            continue
        bucket = aggregates.setdefault(
            entry.collaborator_id,
            {
                "mecanico": str(entry.collaborator),
                "qtd_os": set(),
                "comissao": Decimal("0.00"),
                "base": Decimal("0.00"),
            },
        )
        if entry.workorder_id:
            bucket["qtd_os"].add(entry.workorder_id)
        bucket["comissao"] += _money_amount(entry.commission_amount)
        bucket["base"] += _money_amount(entry.base_amount)
    rows = [
        {
            "mecanico": data["mecanico"],
            "qtd_os": len(data["qtd_os"]),
            "base": data["base"],
            "comissao": data["comissao"],
        }
        for data in aggregates.values()
    ]
    rows.sort(key=lambda r: Decimal(str(r["comissao"])), reverse=True)
    columns = [
        ReportColumnDef("mecanico", "Mecânico", width=32),
        ReportColumnDef("qtd_os", "Qtd. OS", align="right", width=12),
        ReportColumnDef("base", "Base OS", kind="money_sale", align="right", width=14),
        ReportColumnDef("comissao", "Comissão", kind="money_profit", align="right", width=14),
    ]
    return ManagementReport(
        report_key="top_mecanicos",
        title="Top mecânicos do mês",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
        total_value=sum((Decimal(str(r["comissao"])) for r in rows), Decimal("0.00")),
        total_label="Comissão total",
    )


def build_total_comissao_periodo(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    qs = _commission_queryset(workshop=workshop, period=period)
    rows: list[dict[str, Any]] = []
    total = Decimal("0.00")
    for entry in qs:
        commission = _money_amount(entry.commission_amount)
        total += commission
        base = _money_amount(entry.base_amount)
        pct = Decimal(str(entry.percentage or 0)) * Decimal("100")
        rows.append(
            {
                "mecanico": str(entry.collaborator) if entry.collaborator_id else "-",
                "os": resolve_workorder_number(entry.workorder) if entry.workorder_id else "-",
                "cliente": str(getattr(getattr(entry.workorder, "budget", None), "customer", None) or "-"),
                "valor_os": base,
                "percentual": pct,
                "comissao": commission,
                "status": entry.get_status_display() if hasattr(entry, "get_status_display") else entry.status,
                "data": entry.criado_em.date() if entry.criado_em else None,
            }
        )
    columns = [
        ReportColumnDef("mecanico", "Mecânico", width=28),
        ReportColumnDef("os", "Nº OS", kind="id", width=12),
        ReportColumnDef("cliente", "Cliente", width=26),
        ReportColumnDef("valor_os", "Valor OS / Base", kind="money_sale", align="right", width=14),
        ReportColumnDef("percentual", "% Comissão", kind="percent", align="right", width=12),
        ReportColumnDef("comissao", "Comissão", kind="money_profit", align="right", width=14),
        ReportColumnDef("status", "Status", kind="badge", width=12),
        ReportColumnDef("data", "Data", kind="date", width=12),
    ]
    return ManagementReport(
        report_key="total_comissao_periodo",
        title="Total de comissão por período",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
        total_value=total,
        total_label="Comissão total",
    )


def build_commission_report(*, workshop: Workshop, period: ReportPeriod, report_key: str) -> ManagementReport | None:
    builders = {
        "top_mecanicos": build_top_mecanicos,
        "total_comissao_periodo": build_total_comissao_periodo,
    }
    builder = builders.get(report_key)
    if builder is None:
        return None
    return builder(workshop=workshop, period=period)
