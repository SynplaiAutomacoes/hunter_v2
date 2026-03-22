from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import unicodedata
from typing import Any, Sequence

from django.db.models import Prefetch, Q, QuerySet
from djmoney.money import Money

from apps.finance.models import FinancialGroup
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import MECHANIC_SALARY_MONTHLY_COST_NAME


_ZERO_MONEY = Money("0.00", "BRL")
_MONEY_QUANTIZER = Decimal("0.01")
_FINANCIAL_EXPENSE_KEYWORDS = ("banc", "emprest", "juros", "financeir")
_MONTH_LABELS = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Marco",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


@dataclass(frozen=True)
class DreCalculationResult:
    rows: list[dict[str, object]]
    summary_cards: list[dict[str, object]]


_ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS = "receita_bruta_vendas_e_servicos"
_ROW_COMPONENT_CUSTOS_MERCADORIAS_VENDIDAS = "custos_mercadorias_vendidas"
_ROW_COMPONENT_RECEITA_BRUTA_DE_VENDAS = "receita_bruta_de_vendas"
_ROW_COMPONENT_RECEITAS_FINANCEIRAS = "receitas_financeiras"
_ROW_COMPONENT_DESPESAS_FINANCEIRAS = "despesas_financeiras"
_ROW_COMPONENT_RESULTADO_OPERACIONAL = "resultado_operacional"
_TIPO_DATA_PAGAMENTO = "PG"
_TIPO_DATA_ENTRADA = "NPG"
_TIPO_DATA_AMBOS = "A"
_VALID_TIPO_DATA = {_TIPO_DATA_PAGAMENTO, _TIPO_DATA_ENTRADA, _TIPO_DATA_AMBOS}


def build_dre_calculation(
    *,
    workshops: Sequence[Workshop],
    start_date: date | None,
    end_date: date | None,
    tipo_data: str = _TIPO_DATA_AMBOS,
    selected_financial_groups: list[FinancialGroup] | None = None,
) -> DreCalculationResult:
    if not workshops or start_date is None or end_date is None or start_date > end_date:
        return DreCalculationResult(rows=_build_rows(), summary_cards=_build_summary_cards())

    workorders = _get_workorders(workshops=workshops, start_date=start_date, end_date=end_date, tipo_data=tipo_data)
    workshop_costs = _get_workshop_costs(workshops=workshops, start_date=start_date, end_date=end_date)
    receita_bruta_vendas_e_servicos = _ZERO_MONEY
    custos_mercadorias_vendidas = _ZERO_MONEY

    for workorder in workorders:
        receita_bruta_vendas_e_servicos += workorder.total_services_value + workorder.total_products_value
        custos_mercadorias_vendidas += workorder.total_costs_products_value + workorder.total_costs_services_value

    receitas_financeiras = _ZERO_MONEY
    despesas_financeiras = _ZERO_MONEY
    for workshop_cost in workshop_costs:
        workshop_cost_items = getattr(workshop_cost, "items").all()
        for item in workshop_cost_items:
            monthly_cost_name = _normalize_label(item.monthly_cost.name)
            if monthly_cost_name == _normalize_label(MECHANIC_SALARY_MONTHLY_COST_NAME):
                continue
            if _is_financial_expense(item.monthly_cost):
                despesas_financeiras += item.amount

    all_amounts = {
        "receita_bruta_vendas_e_servicos": receita_bruta_vendas_e_servicos,
        "custos_mercadorias_vendidas": custos_mercadorias_vendidas,
        "receitas_financeiras": receitas_financeiras,
        "despesas_financeiras": despesas_financeiras,
    }

    visible_components = _resolve_visible_components(selected_financial_groups=selected_financial_groups)
    visible_amounts = {key: amount if key in visible_components else _ZERO_MONEY for key, amount in all_amounts.items()}
    receita_bruta_de_vendas = visible_amounts["receita_bruta_vendas_e_servicos"] - visible_amounts["custos_mercadorias_vendidas"]
    resultado_operacional = visible_amounts["receitas_financeiras"] - visible_amounts["despesas_financeiras"]
    row_details = _build_row_details(
        workorders=workorders,
        workshop_costs=workshop_costs,
        visible_components=visible_components,
        all_amounts=visible_amounts,
        receita_bruta_de_vendas=receita_bruta_de_vendas,
        resultado_operacional=resultado_operacional,
    )

    return DreCalculationResult(
        rows=_build_rows(
            receita_bruta_vendas_e_servicos=visible_amounts["receita_bruta_vendas_e_servicos"],
            custos_mercadorias_vendidas=visible_amounts["custos_mercadorias_vendidas"],
            receita_bruta_de_vendas=receita_bruta_de_vendas,
            receitas_financeiras=visible_amounts["receitas_financeiras"],
            despesas_financeiras=visible_amounts["despesas_financeiras"],
            resultado_operacional=resultado_operacional,
            row_details=row_details,
        ),
        summary_cards=_build_summary_cards(
            receita_bruta_de_vendas=receita_bruta_de_vendas,
            resultado_operacional=resultado_operacional,
        ),
    )


def _get_workorders(*, workshops: Sequence[Workshop], start_date: date, end_date: date, tipo_data: str) -> list[WorkOrder]:
    queryset = (
        WorkOrder.objects.filter(workshop__in=workshops)
        .exclude(status__in=[WorkOrderStatus.REJECTED, WorkOrderStatus.CANCELLED])
        .select_related("budget", "budget__customer")
        .prefetch_related(
            "payments",
            "items",
            "items__product",
            "items__service",
            "items__kit",
            "items__kit_overrides",
            "items__kit__kit_products__product",
            "items__kit__kit_services__service",
        )
    )
    return list(_filter_workorders_by_tipo_data(queryset=queryset, start_date=start_date, end_date=end_date, tipo_data=tipo_data).order_by("criado_em", "pk"))


def _filter_workorders_by_tipo_data(*, queryset: QuerySet[WorkOrder], start_date: date, end_date: date, tipo_data: str) -> QuerySet[WorkOrder]:
    entry_date_filter = Q(budget__entry_date__range=(start_date, end_date))
    payment_date_filter = Q(payments__due_date__range=(start_date, end_date))
    normalized_tipo_data = _normalize_tipo_data(tipo_data)

    if normalized_tipo_data == _TIPO_DATA_PAGAMENTO:
        return queryset.filter(payment_date_filter).distinct()
    if normalized_tipo_data == _TIPO_DATA_ENTRADA:
        return queryset.filter(entry_date_filter)
    return queryset.filter(entry_date_filter | payment_date_filter).distinct()


def _normalize_tipo_data(tipo_data: str) -> str:
    normalized_tipo_data = str(tipo_data or "").strip().upper()
    if normalized_tipo_data in _VALID_TIPO_DATA:
        return normalized_tipo_data
    return _TIPO_DATA_AMBOS


def _get_workshop_costs(*, workshops: Sequence[Workshop], start_date: date, end_date: date) -> list[WorkshopCost]:
    workshop_costs = WorkshopCost.objects.filter(workshop__in=workshops, year__gte=start_date.year, year__lte=end_date.year).prefetch_related(Prefetch("items", queryset=WorkshopCostItem.objects.select_related("monthly_cost"))).order_by("year", "month", "pk")
    return [workshop_cost for workshop_cost in workshop_costs if _month_overlaps_range(workshop_cost=workshop_cost, start_date=start_date, end_date=end_date)]


def _month_overlaps_range(*, workshop_cost: WorkshopCost, start_date: date, end_date: date) -> bool:
    month_start = date(workshop_cost.year, workshop_cost.month, 1)
    if workshop_cost.month == 12:
        month_end = date(workshop_cost.year + 1, 1, 1)
    else:
        month_end = date(workshop_cost.year, workshop_cost.month + 1, 1)
    return month_start <= end_date and month_end > start_date


def _build_rows(
    *,
    receita_bruta_vendas_e_servicos: Money = _ZERO_MONEY,
    custos_mercadorias_vendidas: Money = _ZERO_MONEY,
    receita_bruta_de_vendas: Money = _ZERO_MONEY,
    receitas_financeiras: Money = _ZERO_MONEY,
    despesas_financeiras: Money = _ZERO_MONEY,
    resultado_operacional: Money = _ZERO_MONEY,
    row_details: dict[str, list[dict[str, object]]] | None = None,
) -> list[dict[str, object]]:
    details = row_details or {}
    return [
        _build_row(
            label="(+) Receita Bruta de Vendas e Serviços",
            amount=receita_bruta_vendas_e_servicos,
            tone="positive",
            component=_ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS,
            detail_kind="workorders",
            is_expandable=True,
            details=details.get(_ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS, []),
        ),
        _build_row(
            label="(-) Custos Mercadorias Vendidas",
            amount=custos_mercadorias_vendidas,
            tone="negative",
            component=_ROW_COMPONENT_CUSTOS_MERCADORIAS_VENDIDAS,
            detail_kind="workorders",
            is_expandable=True,
            details=details.get(_ROW_COMPONENT_CUSTOS_MERCADORIAS_VENDIDAS, []),
        ),
        _build_row(
            label="(=) Receita Bruta de Vendas",
            amount=receita_bruta_de_vendas,
            tone="highlight",
            formula="(Receita Bruta de Vendas e Serviços - Custos Mercadorias Vendidas)",
            component=_ROW_COMPONENT_RECEITA_BRUTA_DE_VENDAS,
            detail_kind="components",
            details=details.get(_ROW_COMPONENT_RECEITA_BRUTA_DE_VENDAS, []),
        ),
        _build_row(
            label="(+) Receitas Financeiras",
            amount=receitas_financeiras,
            tone="positive",
            component=_ROW_COMPONENT_RECEITAS_FINANCEIRAS,
            detail_kind="financial_entries",
            is_expandable=True,
            details=details.get(_ROW_COMPONENT_RECEITAS_FINANCEIRAS, []),
        ),
        _build_row(
            label="(-) Despesas Financeiras",
            amount=despesas_financeiras,
            tone="negative",
            component=_ROW_COMPONENT_DESPESAS_FINANCEIRAS,
            detail_kind="financial_entries",
            is_expandable=True,
            details=details.get(_ROW_COMPONENT_DESPESAS_FINANCEIRAS, []),
        ),
        _build_row(
            label="(=) Resultado Operacional",
            amount=resultado_operacional,
            tone="result",
            formula="(Receitas Financeiras - Despesas Financeiras)",
            component=_ROW_COMPONENT_RESULTADO_OPERACIONAL,
            detail_kind="components",
            details=details.get(_ROW_COMPONENT_RESULTADO_OPERACIONAL, []),
        ),
    ]


def _build_summary_cards(
    *,
    receita_bruta_de_vendas: Money = _ZERO_MONEY,
    resultado_operacional: Money = _ZERO_MONEY,
) -> list[dict[str, object]]:
    return [
        {"label": "Receita Bruta de Vendas", "amount": receita_bruta_de_vendas, "accent": "text-sky-700"},
        {"label": "Resultado Operacional", "amount": resultado_operacional, "accent": "text-amber-700"},
    ]


def _resolve_visible_components(*, selected_financial_groups: list[FinancialGroup] | None) -> set[str]:
    all_components = {
        "receita_bruta_vendas_e_servicos",
        "custos_mercadorias_vendidas",
        "receitas_financeiras",
        "despesas_financeiras",
    }
    if not selected_financial_groups:
        return all_components

    selected_names = {_normalize_label(group.name) for group in selected_financial_groups}
    visible_components: set[str] = set()

    if {"receitas", "receitas de servicos", "receitas de pecas", "receita bruta de vendas e servicos", "receita bruta de vendas e serviços"} & selected_names:
        visible_components.add("receita_bruta_vendas_e_servicos")
    if {"custos", "custos de pecas", "custos de servicos", "custos mercadorias vendidas"} & selected_names:
        visible_components.add("custos_mercadorias_vendidas")
    if {"receitas financeiras", "receitas outras", "receitas"} & selected_names:
        visible_components.add("receitas_financeiras")
    if {"despesas", "despesas financeiras"} & selected_names:
        visible_components.add("despesas_financeiras")

    return visible_components


def _is_financial_expense(monthly_cost: MonthlyCost) -> bool:
    normalized_name = _normalize_label(monthly_cost.name)
    return any(keyword in normalized_name for keyword in _FINANCIAL_EXPENSE_KEYWORDS)


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(character for character in normalized if not unicodedata.combining(character)).casefold().strip()


def _quantize_money(value: Decimal) -> Money:
    return Money(value.quantize(_MONEY_QUANTIZER, rounding=ROUND_HALF_UP), "BRL")


def _build_row_details(
    *,
    workorders: list[WorkOrder],
    workshop_costs: list[WorkshopCost],
    visible_components: set[str],
    all_amounts: dict[str, Money],
    receita_bruta_de_vendas: Money,
    resultado_operacional: Money,
) -> dict[str, list[dict[str, object]]]:
    details: dict[str, list[dict[str, object]]] = {}

    if _ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS in visible_components:
        revenue_details = [_build_workorder_detail(workorder=workorder, amount=workorder.total_services_value + workorder.total_products_value) for workorder in workorders]
        if revenue_details:
            details[_ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS] = revenue_details

    if _ROW_COMPONENT_CUSTOS_MERCADORIAS_VENDIDAS in visible_components:
        cost_details = [_build_workorder_detail(workorder=workorder, amount=workorder.total_costs_products_value + workorder.total_costs_services_value) for workorder in workorders]
        if cost_details:
            details[_ROW_COMPONENT_CUSTOS_MERCADORIAS_VENDIDAS] = cost_details

    financial_expense_details = _build_financial_expense_details(workshop_costs=workshop_costs)
    if _ROW_COMPONENT_DESPESAS_FINANCEIRAS in visible_components and financial_expense_details:
        details[_ROW_COMPONENT_DESPESAS_FINANCEIRAS] = financial_expense_details

    return details


def _build_workorder_detail(*, workorder: WorkOrder, amount: Money) -> dict[str, object]:
    customer_name = getattr(getattr(workorder, "budget", None), "customer", None)
    latest_payment_date = _get_latest_payment_due_date(workorder=workorder)
    return {
        "workorder_id": workorder.pk,
        "summary": f"OS/PEDIDO Nº {workorder.pk} - {customer_name or '-'}",
        "entry_date": getattr(workorder.budget, "entry_date", None),
        "payment_date": latest_payment_date,
        "amount": amount,
    }


def _build_financial_expense_details(*, workshop_costs: list[WorkshopCost]) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    for workshop_cost in workshop_costs:
        for item in getattr(workshop_cost, "items").all():
            monthly_cost_name = _normalize_label(item.monthly_cost.name)
            if monthly_cost_name == _normalize_label(MECHANIC_SALARY_MONTHLY_COST_NAME):
                continue
            if not _is_financial_expense(item.monthly_cost):
                continue
            details.append(
                {
                    "summary": item.monthly_cost.name,
                    "reference": f"{_MONTH_LABELS.get(workshop_cost.month, str(workshop_cost.month))}/{workshop_cost.year}",
                    "amount": item.amount,
                }
            )
    return details


def _get_latest_payment_due_date(*, workorder: WorkOrder) -> date | None:
    payments = list(getattr(workorder, "payments").all())
    payment_dates = [payment.due_date for payment in payments if payment.due_date]
    return max(payment_dates, default=None)


def _build_row(
    *,
    label: str,
    amount: Money,
    tone: str,
    formula: str | None = None,
    component: str | None = None,
    detail_kind: str | None = None,
    is_expandable: bool = False,
    details: list[dict[str, object]] | None = None,
) -> dict[str, Any]:
    return {
        "label": label,
        "amount": amount,
        "tone": tone,
        "formula": formula,
        "component": component,
        "detail_kind": detail_kind,
        "is_expandable": is_expandable,
        "details": details or [],
    }
