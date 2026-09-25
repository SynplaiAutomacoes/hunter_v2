from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import Q

from apps.budget.models import Budget, BudgetStatus
from apps.core.infrastructure.kit_prefetch import budget_items_with_kit_prefetch
from apps.core.infrastructure.services.dashboard_query_service import (
    _build_injected_pricing_context,
    _prepare_budget_for_dashboard_pricing,
)
from apps.core.infrastructure.services.management_reports.period import ReportPeriod
from apps.core.infrastructure.services.management_reports.types import ManagementReport, ReportColumnDef
from apps.core.workorder_numbers import resolve_budget_workorder_number, resolve_workorder_number
from apps.workorder.models import WorkOrder, WorkOrderCourtesyReasonType, WorkOrderStatus
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop


RETRABALHO_REASON_TYPES = frozenset(
    {
        WorkOrderCourtesyReasonType.LABOR_FAILURE,
        WorkOrderCourtesyReasonType.BOTH,
    }
)


def _money_amount(value: object) -> Decimal:
    amount = getattr(value, "amount", value)
    if amount is None:
        return Decimal("0.00")
    return Decimal(str(amount))


def _vehicle_fields(vehicle: object | None) -> tuple[str, str]:
    if vehicle is None:
        return "-", "-"
    plate = str(getattr(vehicle, "plate", None) or "-")
    model = str(getattr(vehicle, "model", None) or "-")
    brand = str(getattr(vehicle, "brand", None) or "").strip()
    if brand and model != "-":
        model = f"{brand} {model}".strip()
    return plate, model


def _workshop_name(workshop: Workshop) -> str:
    return workshop.pdf_name or workshop.name or "-"


def _workorder_cost_loss(workorder: WorkOrder, *, reason_type: str | None) -> Decimal:
    """Workshop loss on a warranty/courtesy OS: labor costs, or labor+parts when reason is both."""
    service_cost = _money_amount(getattr(workorder, "total_costs_services_value", None))
    third_party_cost = _money_amount(getattr(workorder, "total_third_party_services_cost", None))
    product_cost = _money_amount(getattr(workorder, "total_costs_products_value", None))
    labor_cost = service_cost + third_party_cost
    if reason_type == WorkOrderCourtesyReasonType.BOTH:
        return labor_cost + product_cost
    return labor_cost


def build_rentabilidade_acumulada(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    workshop_cost = WorkshopCost.objects.filter(workshop=workshop, month=period.month, year=period.year).first()
    pricing_context = _build_injected_pricing_context(workshop=workshop, workshop_cost=workshop_cost)

    qs = (
        WorkOrder.objects.filter(
            workshop=workshop,
            status=WorkOrderStatus.APPROVED,
            delivered_at__isnull=False,
            delivered_at__month=period.month,
            delivered_at__year=period.year,
            budget_id__isnull=False,
        )
        .exclude(budget_type__in=["warranty", "courtesy"])
        .select_related("budget", "budget__customer", "budget__vehicle", "budget__workshop")
        .prefetch_related(budget_items_with_kit_prefetch(lookup="budget__items"))
        .order_by("-delivered_at", "-pk")
    )
    rows: list[dict[str, Any]] = []
    for wo in qs:
        budget = wo.budget
        plate, model = _vehicle_fields(getattr(budget, "vehicle", None) if budget else None)
        if budget is not None:
            _prepare_budget_for_dashboard_pricing(budget, pricing_context=pricing_context, for_totals_only=True)
        rentability = getattr(budget, "rentability", None) if budget else None
        gross = _money_amount(getattr(wo, "stored_total_amount", None))
        rows.append(
            {
                "os": resolve_workorder_number(wo),
                "cliente": str(getattr(budget, "customer", None) or "-"),
                "placa": plate,
                "modelo": model,
                "data": wo.delivered_at.date() if wo.delivered_at else None,
                "valor_bruto": gross,
                "rentabilidade": Decimal(str(rentability or 0)),
            }
        )
    columns = [
        ReportColumnDef("os", "Nº OS", kind="id", width=14),
        ReportColumnDef("cliente", "Cliente", width=32),
        ReportColumnDef("placa", "Placa", width=12),
        ReportColumnDef("modelo", "Modelo do veículo", width=28),
        ReportColumnDef("data", "Entrega", kind="date", width=14),
        ReportColumnDef("valor_bruto", "Valor", kind="money_sale", align="right", width=16),
        ReportColumnDef("rentabilidade", "Rentabilidade %", kind="percent", align="right", width=16),
    ]
    return ManagementReport(
        report_key="rentabilidade_acumulada",
        title="Rentabilidade Acumulada",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
    )


def build_retorno_garantia(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    qs = (
        WorkOrder.objects.filter(
            workshop=workshop,
            budget_type__in=["warranty", "courtesy"],
            status=WorkOrderStatus.APPROVED,
            delivered_at__month=period.month,
            delivered_at__year=period.year,
        )
        .select_related(
            "budget",
            "budget__customer",
            "budget__vehicle",
            "previous_mechanic",
            "warranty_origin",
            "warranty_origin__budget",
        )
        .prefetch_related("collaborators", "warranty_origin__collaborators")
        .order_by("-delivered_at", "-pk")
    )
    rows: list[dict[str, Any]] = []
    for wo in qs:
        budget = wo.budget
        plate, model = _vehicle_fields(getattr(budget, "vehicle", None) if budget else None)
        mechanic = wo.previous_mechanic
        if mechanic is None and wo.warranty_origin_id:
            mechanic = wo.warranty_origin.collaborators.first()
        if mechanic is None:
            mechanic = wo.collaborators.first()
        total = _money_amount(getattr(wo, "stored_total_amount", None) or getattr(wo, "total_budget_value", None))
        cost = Decimal("0.00")
        if hasattr(wo, "total_costs_value"):
            cost = _money_amount(wo.total_costs_value)
        elif hasattr(wo, "pricing_snapshot"):
            snapshot = getattr(wo, "pricing_snapshot", None)
            if snapshot is not None:
                cost = _money_amount(getattr(snapshot, "total_costs_value", None))
        rows.append(
            {
                "os": resolve_workorder_number(wo),
                "tipo": wo.get_budget_type_display() if hasattr(wo, "get_budget_type_display") else wo.budget_type,
                "cliente": str(getattr(budget, "customer", None) or "-"),
                "placa": plate,
                "modelo": model,
                "mecanico": str(mechanic) if mechanic else "-",
                "motivo": wo.get_courtesy_reason_type_display() if wo.courtesy_reason_type else "-",
                "valor_total": total,
                "custo": cost,
                "data": wo.delivered_at.date() if wo.delivered_at else None,
            }
        )
    columns = [
        ReportColumnDef("os", "Nº OS", kind="id", width=14),
        ReportColumnDef("tipo", "Tipo", kind="badge", width=14),
        ReportColumnDef("cliente", "Cliente", width=28),
        ReportColumnDef("placa", "Placa", width=12),
        ReportColumnDef("modelo", "Modelo do veículo", width=24),
        ReportColumnDef("mecanico", "Mecânico", width=24),
        ReportColumnDef("motivo", "Motivo", width=22),
        ReportColumnDef("valor_total", "Valor OS", kind="money_sale", align="right", width=14),
        ReportColumnDef("custo", "Custo OS", kind="money_cost", align="right", width=14),
        ReportColumnDef("data", "Entrega", kind="date", width=14),
    ]
    return ManagementReport(
        report_key="retorno_garantia",
        title="Retorno em Garantia",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
    )


def build_taxa_aprovacao(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    qs = (
        Budget.objects.filter(
            workshop=workshop,
            entry_date__month=period.month,
            entry_date__year=period.year,
        )
        .exclude(budget_type__in=["warranty", "courtesy"])
        .filter(
            Q(status=BudgetStatus.APPROVED)
            | Q(status=BudgetStatus.REJECTED)
            | Q(status=BudgetStatus.CANCELLED)
            | Q(status__in=["reprovado", "reproved"])
        )
        .select_related("customer", "vehicle")
        .order_by("-entry_date", "-pk")
    )
    rows: list[dict[str, Any]] = []
    for budget in qs:
        plate, model = _vehicle_fields(budget.vehicle)
        status = budget.status
        if status in ("reprovado", "reproved", BudgetStatus.REJECTED):
            status_label = "Reprovado"
            reason = budget.rejection_reason or "-"
        elif status == BudgetStatus.CANCELLED:
            status_label = "Cancelado"
            reason = "-"
        else:
            status_label = "Aprovado"
            reason = "-"
        rows.append(
            {
                "os": resolve_budget_workorder_number(budget),
                "cliente": str(budget.customer or "-"),
                "placa": plate,
                "modelo": model,
                "status": status_label,
                "motivo": reason,
                "valor": _money_amount(getattr(budget, "stored_total_amount", None) or getattr(budget, "total_budget_value", None)),
                "data": budget.entry_date,
            }
        )
    columns = [
        ReportColumnDef("os", "Nº Orçamento/OS", kind="id", width=16),
        ReportColumnDef("cliente", "Cliente", width=28),
        ReportColumnDef("placa", "Placa", width=12),
        ReportColumnDef("modelo", "Modelo do veículo", width=24),
        ReportColumnDef("status", "Status", kind="badge", width=14),
        ReportColumnDef("motivo", "Motivo", width=28),
        ReportColumnDef("valor", "Valor", kind="money_sale", align="right", width=14),
        ReportColumnDef("data", "Data", kind="date", width=14),
    ]
    return ManagementReport(
        report_key="taxa_aprovacao",
        title="Taxa de Aprovação",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
    )


def build_mecanicos_retrabalho(*, workshop: Workshop, period: ReportPeriod, sort_by: str = "perda") -> ManagementReport:
    """Rank mechanics by warranty/courtesy OS caused by labor failure or both (labor + parts)."""
    benefit_wos = list(
        WorkOrder.objects.filter(
            workshop=workshop,
            budget_type__in=("warranty", "courtesy"),
            status=WorkOrderStatus.APPROVED,
            delivered_at__month=period.month,
            delivered_at__year=period.year,
            courtesy_reason_type__in=RETRABALHO_REASON_TYPES,
        )
        .select_related("previous_mechanic", "warranty_origin", "budget", "budget__vehicle")
        .prefetch_related("warranty_origin__collaborators")
    )

    aggregates: dict[int, dict[str, Any]] = {}

    for benefit in benefit_wos:
        mechanic = benefit.previous_mechanic
        if mechanic is None and benefit.warranty_origin_id:
            mechanic = benefit.warranty_origin.collaborators.first()
        if mechanic is None:
            continue

        loss = _workorder_cost_loss(benefit, reason_type=benefit.courtesy_reason_type)

        if mechanic.pk not in aggregates:
            aggregates[mechanic.pk] = {
                "mecanico": str(mechanic),
                "qtd_veiculos": 0,
                "perda": Decimal("0.00"),
                "os_ids": [],
            }
        aggregates[mechanic.pk]["qtd_veiculos"] += 1
        aggregates[mechanic.pk]["perda"] += loss
        aggregates[mechanic.pk]["os_ids"].append(str(resolve_workorder_number(benefit)))

    rows = list(aggregates.values())
    for row in rows:
        row["os_lista"] = ", ".join(row.pop("os_ids"))
    if sort_by == "veiculos":
        rows.sort(key=lambda r: (int(r["qtd_veiculos"]), Decimal(str(r["perda"]))), reverse=True)
    else:
        rows.sort(key=lambda r: (Decimal(str(r["perda"])), int(r["qtd_veiculos"])), reverse=True)

    columns = [
        ReportColumnDef("mecanico", "Mecânico", width=32),
        ReportColumnDef("qtd_veiculos", "Qtd. veículos", align="right", width=14),
        ReportColumnDef("perda", "Prejuízo acumulado", kind="money_cost", align="right", width=18),
        ReportColumnDef("os_lista", "OS de retrabalho", width=40),
    ]
    return ManagementReport(
        report_key="mecanicos_retrabalho",
        title="Mecânicos que mais geram retrabalhos",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
        sort_options=[
            {"value": "perda", "label": "Valor de prejuízo"},
            {"value": "veiculos", "label": "Quantidade de veículos"},
        ],
        selected_sort=sort_by if sort_by in {"perda", "veiculos"} else "perda",
        total_value=sum((Decimal(str(r["perda"])) for r in rows), Decimal("0.00")),
        total_label="Prejuízo total",
    )


def build_performance_report(*, workshop: Workshop, period: ReportPeriod, report_key: str, sort_by: str = "perda") -> ManagementReport | None:
    builders = {
        "rentabilidade_acumulada": lambda: build_rentabilidade_acumulada(workshop=workshop, period=period),
        "retorno_garantia": lambda: build_retorno_garantia(workshop=workshop, period=period),
        "taxa_aprovacao": lambda: build_taxa_aprovacao(workshop=workshop, period=period),
        "mecanicos_retrabalho": lambda: build_mecanicos_retrabalho(workshop=workshop, period=period, sort_by=sort_by),
    }
    builder = builders.get(report_key)
    if builder is None:
        return None
    return builder()
