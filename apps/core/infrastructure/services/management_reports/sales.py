from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db.models import DecimalField, ExpressionWrapper, F

from apps.budget.models import REVENUE_BUDGET_TYPES
from apps.core.infrastructure.services.management_reports.period import ReportPeriod
from apps.core.infrastructure.services.management_reports.types import ManagementReport, ReportColumnDef
from apps.core.workorder_numbers import resolve_workorder_number
from apps.finance.models.financial_movement import FinancialMovement
from apps.workorder.models import WORKORDER_REVENUE_STATUSES, WorkOrder, WorkOrderItem, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def _money_amount(value: object) -> Decimal:
    amount = getattr(value, "amount", value)
    if amount is None:
        return Decimal("0.00")
    return Decimal(str(amount))


def _workshop_name(workshop: Workshop) -> str:
    return workshop.pdf_name or workshop.name or "-"


def _vehicle_fields(vehicle: object | None) -> tuple[str, str]:
    if vehicle is None:
        return "-", "-"
    plate = str(getattr(vehicle, "plate", None) or "-")
    model = str(getattr(vehicle, "model", None) or "-")
    brand = str(getattr(vehicle, "brand", None) or "").strip()
    if brand and model != "-":
        model = f"{brand} {model}".strip()
    return plate, model


def _delivered_sale_workorders(*, workshop: Workshop, period: ReportPeriod):
    return (
        WorkOrder.objects.filter(
            workshop=workshop,
            status=WorkOrderStatus.APPROVED,
            budget_type__in=REVENUE_BUDGET_TYPES,
            delivered_at__month=period.month,
            delivered_at__year=period.year,
        )
        .select_related("budget", "budget__customer", "budget__vehicle")
        .order_by("-delivered_at", "-pk")
    )


def build_total_vendas_os(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    rows: list[dict[str, Any]] = []
    total_bruto = Decimal("0.00")
    total_liquido = Decimal("0.00")
    for wo in _delivered_sale_workorders(workshop=workshop, period=period):
        plate, model = _vehicle_fields(getattr(wo.budget, "vehicle", None) if wo.budget_id else None)
        bruto = _money_amount(getattr(wo, "stored_total_amount", None) or getattr(wo, "total_budget_value", None))
        desconto = _money_amount(getattr(wo, "resolved_discount_value", None) if hasattr(wo, "resolved_discount_value") else None)
        liquido = bruto - desconto if desconto else bruto
        total_bruto += bruto
        total_liquido += liquido
        rows.append(
            {
                "os": resolve_workorder_number(wo),
                "cliente": str(getattr(wo.budget, "customer", None) or "-"),
                "placa": plate,
                "modelo": model,
                "data": wo.delivered_at.date() if wo.delivered_at else None,
                "bruto": bruto,
                "liquido": liquido,
            }
        )
    columns = [
        ReportColumnDef("os", "Nº OS", kind="id", width=14),
        ReportColumnDef("cliente", "Cliente", width=30),
        ReportColumnDef("placa", "Placa", width=12),
        ReportColumnDef("modelo", "Modelo do veículo", width=24),
        ReportColumnDef("data", "Entrega", kind="date", width=14),
        ReportColumnDef("bruto", "Valor bruto", kind="money_sale", align="right", width=14),
        ReportColumnDef("liquido", "Valor líquido", kind="money_profit", align="right", width=14),
    ]
    return ManagementReport(
        report_key="total_vendas_os",
        title="Total vendas OS",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
        summary_cards=[
            {"label": "Bruto", "value": str(total_bruto)},
            {"label": "Líquido", "value": str(total_liquido)},
        ],
        total_value=total_liquido,
        total_label="Total líquido",
    )


def build_top_clientes(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    aggregates: dict[int, dict[str, Any]] = {}
    for wo in _delivered_sale_workorders(workshop=workshop, period=period):
        customer = getattr(wo.budget, "customer", None) if wo.budget_id else None
        if customer is None:
            continue
        bucket = aggregates.setdefault(
            customer.pk,
            {"cliente": str(customer), "qtd_os": 0, "total": Decimal("0.00")},
        )
        bucket["qtd_os"] += 1
        bucket["total"] += _money_amount(getattr(wo, "stored_total_amount", None) or getattr(wo, "total_budget_value", None))
    rows = sorted(aggregates.values(), key=lambda r: Decimal(str(r["total"])), reverse=True)
    columns = [
        ReportColumnDef("cliente", "Cliente", width=40),
        ReportColumnDef("qtd_os", "Qtd. OS", align="right", width=12),
        ReportColumnDef("total", "Vendas acumuladas", kind="money_sale", align="right", width=18),
    ]
    return ManagementReport(
        report_key="top_clientes",
        title="Top Clientes",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
        total_value=sum((Decimal(str(r["total"])) for r in rows), Decimal("0.00")),
        total_label="Total",
    )


def _build_line_sales(*, workshop: Workshop, period: ReportPeriod, line: str) -> ManagementReport:
    filter_kwargs: dict[str, Any] = {
        "workshop": workshop,
        "workorder__status": WorkOrderStatus.APPROVED,
        "workorder__budget_type": "sale",
        "workorder__delivered_at__month": period.month,
        "workorder__delivered_at__year": period.year,
    }
    if line == "service":
        filter_kwargs["service_id__isnull"] = False
        title = "Total vendas de serviços"
        key = "vendas_servicos"
        name_attr = "service"
        price_attr = "service_selling_price"
        cost_attr = "service_cost_price"
    else:
        filter_kwargs["product_id__isnull"] = False
        title = "Total vendas de peças"
        key = "vendas_pecas"
        name_attr = "product"
        price_attr = "product_selling_price"
        cost_attr = "product_cost_price"

    items = (
        WorkOrderItem.objects.filter(**filter_kwargs)
        .select_related(name_attr, "workorder", "workorder__budget", "workorder__budget__vehicle", "workorder__budget__customer")
        .order_by("-workorder__delivered_at")
    )
    rows: list[dict[str, Any]] = []
    total_bruto = Decimal("0.00")
    total_custo = Decimal("0.00")
    for item in items:
        wo = item.workorder
        plate, model = _vehicle_fields(getattr(wo.budget, "vehicle", None) if wo.budget_id else None)
        qty = int(item.quantity or 0)
        unit = _money_amount(getattr(item, price_attr))
        cost = _money_amount(getattr(item, cost_attr))
        bruto = unit * qty
        custo = cost * qty
        total_bruto += bruto
        total_custo += custo
        entity = getattr(item, name_attr)
        rows.append(
            {
                "os": resolve_workorder_number(wo),
                "item": str(entity) if entity else (item.description or "-"),
                "cliente": str(getattr(wo.budget, "customer", None) or "-"),
                "placa": plate,
                "modelo": model,
                "quantidade": qty,
                "bruto": bruto,
                "custo": custo,
                "liquido": bruto - custo,
            }
        )
    columns = [
        ReportColumnDef("os", "Nº OS", kind="id", width=12),
        ReportColumnDef("item", "Item", width=30),
        ReportColumnDef("cliente", "Cliente", width=24),
        ReportColumnDef("placa", "Placa", width=12),
        ReportColumnDef("modelo", "Modelo do veículo", width=22),
        ReportColumnDef("quantidade", "Qtd.", align="right", width=10),
        ReportColumnDef("bruto", "Bruto", kind="money_sale", align="right", width=14),
        ReportColumnDef("custo", "Custo", kind="money_cost", align="right", width=14),
        ReportColumnDef("liquido", "Líquido", kind="money_profit", align="right", width=14),
    ]
    return ManagementReport(
        report_key=key,
        title=title,
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
        summary_cards=[
            {"label": "Bruto", "value": str(total_bruto)},
            {"label": "Líquido", "value": str(total_bruto - total_custo)},
        ],
        total_value=total_bruto - total_custo,
        total_label="Total líquido",
    )


def build_taxas_cartao(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    movements = (
        FinancialMovement.objects.filter(
            workshop=workshop,
            description="Pagamento da taxa da maquininha",
            due_date__month=period.month,
            due_date__year=period.year,
        )
        .select_related("workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle", "workorder_payment")
        .order_by("-due_date")
    )
    sales = build_total_vendas_os(workshop=workshop, period=period)
    gross_sales = sum((Decimal(str(r["bruto"])) for r in sales.rows), Decimal("0.00"))
    net_sales = sum((Decimal(str(r["liquido"])) for r in sales.rows), Decimal("0.00"))
    rows: list[dict[str, Any]] = []
    total_fee = Decimal("0.00")
    for movement in movements:
        fee = _money_amount(movement.amount)
        total_fee += fee
        wo = movement.workorder
        plate, model = ("-", "-")
        cliente = "-"
        os_number = "-"
        if wo is not None:
            os_number = str(resolve_workorder_number(wo))
            plate, model = _vehicle_fields(getattr(wo.budget, "vehicle", None) if wo.budget_id else None)
            cliente = str(getattr(wo.budget, "customer", None) or "-")
        rows.append(
            {
                "os": os_number,
                "cliente": cliente,
                "placa": plate,
                "modelo": model,
                "data": movement.due_date,
                "taxa": fee,
            }
        )
    pct_bruto = (total_fee / gross_sales * Decimal("100")) if gross_sales else Decimal("0.00")
    pct_liquido = (total_fee / net_sales * Decimal("100")) if net_sales else Decimal("0.00")
    columns = [
        ReportColumnDef("os", "Nº OS", kind="id", width=12),
        ReportColumnDef("cliente", "Cliente", width=28),
        ReportColumnDef("placa", "Placa", width=12),
        ReportColumnDef("modelo", "Modelo do veículo", width=22),
        ReportColumnDef("data", "Data", kind="date", width=14),
        ReportColumnDef("taxa", "Taxa", kind="money_cost", align="right", width=14),
    ]
    return ManagementReport(
        report_key="taxas_cartao",
        title="Total de taxas de cartão",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
        summary_cards=[
            {"label": "Total taxas", "value": str(total_fee)},
            {"label": "% sobre bruto", "value": f"{pct_bruto.quantize(Decimal('0.01'))}%"},
            {"label": "% sobre líquido", "value": f"{pct_liquido.quantize(Decimal('0.01'))}%"},
        ],
        total_value=total_fee,
        total_label="Total de taxas",
    )


def build_vendas_modalidade(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    payment_expr = ExpressionWrapper(
        F("first_installment_amount") + (F("installments_count") - 1) * F("remaining_installments_amount"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    payments = (
        WorkOrderPaymentMethod.objects.filter(
            workorder__workshop=workshop,
            workorder__status__in=WORKORDER_REVENUE_STATUSES,
            workorder__budget_type__in=REVENUE_BUDGET_TYPES,
            due_date__month=period.month,
            due_date__year=period.year,
        )
        .select_related("payment_method", "workorder", "workorder__budget", "workorder__budget__customer", "workorder__budget__vehicle")
        .annotate(payment_total=payment_expr)
        .order_by("payment_method__description", "-due_date")
    )
    rows: list[dict[str, Any]] = []
    for payment in payments:
        wo = payment.workorder
        plate, model = _vehicle_fields(getattr(wo.budget, "vehicle", None) if wo and wo.budget_id else None)
        rows.append(
            {
                "modalidade": str(payment.payment_method) if payment.payment_method_id else "-",
                "os": resolve_workorder_number(wo) if wo else "-",
                "cliente": str(getattr(wo.budget, "customer", None) or "-") if wo else "-",
                "placa": plate,
                "modelo": model,
                "data": payment.due_date,
                "valor": _money_amount(payment.payment_total),
            }
        )
    columns = [
        ReportColumnDef("modalidade", "Modalidade", width=22),
        ReportColumnDef("os", "Nº OS", kind="id", width=12),
        ReportColumnDef("cliente", "Cliente", width=28),
        ReportColumnDef("placa", "Placa", width=12),
        ReportColumnDef("modelo", "Modelo do veículo", width=22),
        ReportColumnDef("data", "Vencimento", kind="date", width=14),
        ReportColumnDef("valor", "Valor", kind="money_sale", align="right", width=14),
    ]
    return ManagementReport(
        report_key="vendas_modalidade",
        title="Vendas por modalidade",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
        total_value=sum((Decimal(str(r["valor"])) for r in rows), Decimal("0.00")),
        total_label="Total",
    )


def build_servicos_mais_vendidos(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    items = WorkOrderItem.objects.filter(
        workshop=workshop,
        service_id__isnull=False,
        workorder__status=WorkOrderStatus.APPROVED,
        workorder__budget_type="sale",
        workorder__delivered_at__month=period.month,
        workorder__delivered_at__year=period.year,
    ).select_related("service")
    aggregates: dict[int, dict[str, Any]] = {}
    for item in items:
        if not item.service_id:
            continue
        bucket = aggregates.setdefault(
            item.service_id,
            {
                "servico": str(item.service),
                "quantidade": 0,
                "faturamento": Decimal("0.00"),
                "custo": Decimal("0.00"),
                "lucro": Decimal("0.00"),
            },
        )
        qty = int(item.quantity or 0)
        sale = _money_amount(item.service_selling_price) * qty
        cost = _money_amount(item.service_cost_price) * qty
        bucket["quantidade"] += qty
        bucket["faturamento"] += sale
        bucket["custo"] += cost
        bucket["lucro"] += sale - cost
    rows = sorted(aggregates.values(), key=lambda r: Decimal(str(r["lucro"])), reverse=True)
    columns = [
        ReportColumnDef("servico", "Serviço", width=40),
        ReportColumnDef("quantidade", "Quantidade", align="right", width=12),
        ReportColumnDef("faturamento", "Faturamento", kind="money_sale", align="right", width=14),
        ReportColumnDef("custo", "Custo", kind="money_cost", align="right", width=14),
        ReportColumnDef("lucro", "Lucro", kind="money_profit", align="right", width=14),
    ]
    return ManagementReport(
        report_key="servicos_mais_vendidos",
        title="Serviços mais vendidos",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=columns,
        rows=rows,
        total_value=sum((Decimal(str(r["lucro"])) for r in rows), Decimal("0.00")),
        total_label="Lucro total",
    )


def build_ticket_medio(*, workshop: Workshop, period: ReportPeriod) -> ManagementReport:
    report = build_total_vendas_os(workshop=workshop, period=period)
    count = len(report.rows)
    total = sum((Decimal(str(r["liquido"])) for r in report.rows), Decimal("0.00"))
    ticket = (total / count) if count else Decimal("0.00")
    return ManagementReport(
        report_key="ticket_medio",
        title="Ticket médio",
        period_label=period.label,
        workshop_name=_workshop_name(workshop),
        columns=report.columns,
        rows=report.rows,
        summary_cards=[
            {"label": "Qtd. OS", "value": str(count)},
            {"label": "Total líquido", "value": str(total)},
            {"label": "Ticket médio", "value": str(ticket.quantize(Decimal("0.01")))},
        ],
        total_value=total,
        total_label="Total líquido",
    )


def build_sales_report(*, workshop: Workshop, period: ReportPeriod, report_key: str) -> ManagementReport | None:
    builders = {
        "total_vendas_os": build_total_vendas_os,
        "top_clientes": build_top_clientes,
        "vendas_servicos": lambda **kwargs: _build_line_sales(line="service", **kwargs),
        "vendas_pecas": lambda **kwargs: _build_line_sales(line="product", **kwargs),
        "taxas_cartao": build_taxas_cartao,
        "vendas_modalidade": build_vendas_modalidade,
        "servicos_mais_vendidos": build_servicos_mais_vendidos,
        "ticket_medio": build_ticket_medio,
    }
    builder = builders.get(report_key)
    if builder is None:
        return None
    result: ManagementReport = builder(workshop=workshop, period=period)
    return result
