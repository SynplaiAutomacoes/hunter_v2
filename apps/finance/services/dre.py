from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import unicodedata
from typing import Any

from django.db.models import Prefetch
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


@dataclass(frozen=True)
class DreCalculationResult:
    rows: list[dict[str, object]]
    summary_cards: list[dict[str, object]]


def build_dre_calculation(
    *,
    workshop: Workshop | None,
    start_date: date | None,
    end_date: date | None,
    selected_financial_groups: list[FinancialGroup] | None = None,
) -> DreCalculationResult:
    if workshop is None or start_date is None or end_date is None or start_date > end_date:
        return DreCalculationResult(rows=_build_rows(), summary_cards=_build_summary_cards())

    workorders = _get_workorders(workshop=workshop, start_date=start_date, end_date=end_date)
    workshop_costs = _get_workshop_costs(workshop=workshop, start_date=start_date, end_date=end_date)
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

    return DreCalculationResult(
        rows=_build_rows(
            receita_bruta_vendas_e_servicos=visible_amounts["receita_bruta_vendas_e_servicos"],
            custos_mercadorias_vendidas=visible_amounts["custos_mercadorias_vendidas"],
            receita_bruta_de_vendas=receita_bruta_de_vendas,
            receitas_financeiras=visible_amounts["receitas_financeiras"],
            despesas_financeiras=visible_amounts["despesas_financeiras"],
            resultado_operacional=resultado_operacional,
        ),
        summary_cards=_build_summary_cards(
            receita_bruta_vendas_e_servicos=visible_amounts["receita_bruta_vendas_e_servicos"],
            receita_bruta_de_vendas=receita_bruta_de_vendas,
            resultado_operacional=resultado_operacional,
        ),
    )


def _get_workorders(*, workshop: Workshop, start_date: date, end_date: date) -> list[WorkOrder]:
    return list(
        WorkOrder.objects.filter(
            workshop=workshop,
            criado_em__date__gte=start_date,
            criado_em__date__lte=end_date,
        )
        .exclude(status__in=[WorkOrderStatus.REJECTED, WorkOrderStatus.CANCELLED])
        .select_related("budget")
        .prefetch_related(
            "items",
            "items__product",
            "items__service",
            "items__kit",
            "items__kit_overrides",
            "items__kit__kit_products__product",
            "items__kit__kit_services__service",
        )
        .order_by("criado_em", "pk")
    )


def _get_workshop_costs(*, workshop: Workshop, start_date: date, end_date: date) -> list[WorkshopCost]:
    workshop_costs = WorkshopCost.objects.filter(workshop=workshop, year__gte=start_date.year, year__lte=end_date.year).prefetch_related(Prefetch("items", queryset=WorkshopCostItem.objects.select_related("monthly_cost"))).order_by("year", "month", "pk")
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
) -> list[dict[str, object]]:
    return [
        _build_row(label="(+) Receita Bruta de Vendas e Serviços", amount=receita_bruta_vendas_e_servicos, tone="positive"),
        _build_row(label="(-) Custos Mercadorias Vendidas", amount=custos_mercadorias_vendidas, tone="negative"),
        _build_row(label="(=) Receita Bruta de Vendas", amount=receita_bruta_de_vendas, tone="highlight", formula="(Receita Bruta de Vendas e Serviços - Custos Mercadorias Vendidas)"),
        _build_row(label="(+) Receitas Financeiras", amount=receitas_financeiras, tone="positive"),
        _build_row(label="(-) Despesas Financeiras", amount=despesas_financeiras, tone="negative"),
        _build_row(label="(=) Resultado Operacional", amount=resultado_operacional, tone="result", formula="(Receitas Financeiras - Despesas Financeiras)"),
    ]


def _build_summary_cards(
    *,
    receita_bruta_vendas_e_servicos: Money = _ZERO_MONEY,
    receita_bruta_de_vendas: Money = _ZERO_MONEY,
    resultado_operacional: Money = _ZERO_MONEY,
) -> list[dict[str, object]]:
    return [
        {"label": "Receita Bruta de Vendas e Serviços", "amount": receita_bruta_vendas_e_servicos, "accent": "text-emerald-700"},
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

    return visible_components or all_components


def _is_financial_expense(monthly_cost: MonthlyCost) -> bool:
    normalized_name = _normalize_label(monthly_cost.name)
    return any(keyword in normalized_name for keyword in _FINANCIAL_EXPENSE_KEYWORDS)


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(character for character in normalized if not unicodedata.combining(character)).casefold().strip()


def _quantize_money(value: Decimal) -> Money:
    return Money(value.quantize(_MONEY_QUANTIZER, rounding=ROUND_HALF_UP), "BRL")


def _build_row(*, label: str, amount: Money, tone: str, formula: str | None = None) -> dict[str, Any]:
    return {
        "label": label,
        "amount": amount,
        "tone": tone,
        "formula": formula,
    }
