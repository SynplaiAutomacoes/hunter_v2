from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import unicodedata
from typing import Any, Sequence

from django.db.models import Q
from djmoney.money import Money

from apps.finance.models import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.workshops.models.workshops import Workshop


_ZERO_MONEY = Money("0.00", "BRL")


@dataclass(frozen=True)
class DreCalculationResult:
    rows: list[dict[str, object]]
    summary_cards: list[dict[str, object]]


_ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS = "gross_revenue"
_ROW_COMPONENT_CUSTOS_MERCADORIAS_VENDIDAS = "cogs"
_ROW_COMPONENT_RECEITA_BRUTA_DE_VENDAS = "receita_bruta_de_vendas"
_ROW_COMPONENT_RECEITAS_FINANCEIRAS = "financial_revenue"
_ROW_COMPONENT_DESPESAS_FINANCEIRAS = "financial_expense"
_ROW_COMPONENT_RESULTADO_OPERACIONAL = "resultado_operacional"
_SOURCE_ROW_COMPONENTS = (
    _ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS,
    _ROW_COMPONENT_CUSTOS_MERCADORIAS_VENDIDAS,
    _ROW_COMPONENT_RECEITAS_FINANCEIRAS,
    _ROW_COMPONENT_DESPESAS_FINANCEIRAS,
)
_VALID_TIPO_DATA_VALUES = {"PG", "NPG", "A"}


def build_dre_calculation(*, workshops: Sequence[Workshop], start_date: date | None, end_date: date | None, tipo_data: str = "A", selected_financial_groups: list[FinancialGroup] | None = None) -> DreCalculationResult:
    if not workshops or start_date is None or end_date is None or start_date > end_date:
        return DreCalculationResult(rows=_build_rows(), summary_cards=_build_summary_cards())

    tipo_data = str(tipo_data or "A").strip().upper()
    if tipo_data not in _VALID_TIPO_DATA_VALUES:
        tipo_data = "A"

    financial_movements = _get_financial_movements(
        workshops=workshops,
        start_date=start_date,
        end_date=end_date,
        tipo_data=tipo_data,
    )

    movements_by_topic = _group_financial_movements_by_topic(financial_movements=financial_movements)

    all_amounts: dict[str, Money] = {}

    for component in _SOURCE_ROW_COMPONENTS:
        total = _ZERO_MONEY

        for movement in movements_by_topic.get(component, []):
            amount = getattr(movement, "amount", None)

            if not isinstance(amount, Money):
                continue

            if movement.direction == FinancialMovement.MovementDirection.DEBIT:
                total -= amount
            else:
                total += amount

        all_amounts[component] = total

    visible_components = _resolve_visible_components(selected_financial_groups=selected_financial_groups)
    visible_amounts = {key: amount if key in visible_components else _ZERO_MONEY for key, amount in all_amounts.items()}
    receita_bruta_de_vendas = visible_amounts[_ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS] + visible_amounts[_ROW_COMPONENT_CUSTOS_MERCADORIAS_VENDIDAS]
    resultado_operacional = receita_bruta_de_vendas + visible_amounts[_ROW_COMPONENT_RECEITAS_FINANCEIRAS] + visible_amounts[_ROW_COMPONENT_DESPESAS_FINANCEIRAS]
    row_details = _build_row_details(
        movements_by_topic=movements_by_topic,
        visible_components=visible_components,
        include_workshop_reference=len(workshops) > 1,
    )
    rows = _build_rows(
        receita_bruta_vendas_e_servicos=visible_amounts[_ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS],
        custos_mercadorias_vendidas=visible_amounts[_ROW_COMPONENT_CUSTOS_MERCADORIAS_VENDIDAS],
        receita_bruta_de_vendas=receita_bruta_de_vendas,
        receitas_financeiras=visible_amounts[_ROW_COMPONENT_RECEITAS_FINANCEIRAS],
        despesas_financeiras=visible_amounts[_ROW_COMPONENT_DESPESAS_FINANCEIRAS],
        resultado_operacional=resultado_operacional,
        row_details=row_details,
    )

    return DreCalculationResult(
        rows=rows,
        summary_cards=_build_summary_cards(
            receita_bruta_de_vendas=receita_bruta_de_vendas,
            resultado_operacional=resultado_operacional,
        ),
    )


def _get_financial_movements(*, workshops: Sequence[Workshop], start_date: date, end_date: date, tipo_data: str) -> list[FinancialMovement]:
    queryset = FinancialMovement.objects.filter(
        workshop__in=workshops,
        due_date__gte=start_date,
        due_date__lte=end_date
    )

    if tipo_data == "PG":
        queryset = queryset.filter(is_paid=True)
    elif tipo_data == "NPG":
        queryset = queryset.filter(is_paid=False)

    return list(queryset.select_related("payment_method", "source", "workshop", "workorder", "budget_plan", "budget_plan__parent", "budget_plan__parent__parent").order_by("due_date", "criado_em", "pk"))


def _group_financial_movements_by_topic(*, financial_movements: list[FinancialMovement]) -> dict[str, list[FinancialMovement]]:
    grouped_movements: dict[str, list[FinancialMovement]] = {component: [] for component in _SOURCE_ROW_COMPONENTS}
    for movement in financial_movements:
        component = _resolve_movement_component(movement=movement)
        if component is None:
            continue
        grouped_movements[component].append(movement)
    return grouped_movements


def _resolve_movement_component(*, movement: FinancialMovement) -> str | None:
    budget_plan = getattr(movement, "budget_plan", None)

    while budget_plan is not None:
        dre_type = getattr(budget_plan, "dre_type", None)
        if dre_type:
            return dre_type
        budget_plan = getattr(budget_plan, "parent", None)

    movement_kind = getattr(movement, "movement_kind", None)

    if movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT:
        return _ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS

    if getattr(movement, "workorder", None) is not None:
        return _ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS

    return None


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
            label="Receita Bruta de Vendas e Serviços",
            amount=receita_bruta_vendas_e_servicos,
            tone="positive",
            component=_ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS,
            detail_kind="financial_entries",
            is_expandable=True,
            details=details.get(_ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS, []),
        ),
        _build_row(
            label="Custos Mercadorias Vendidas",
            amount=custos_mercadorias_vendidas,
            tone="negative",
            component=_ROW_COMPONENT_CUSTOS_MERCADORIAS_VENDIDAS,
            detail_kind="financial_entries",
            is_expandable=True,
            details=details.get(_ROW_COMPONENT_CUSTOS_MERCADORIAS_VENDIDAS, []),
        ),
        _build_row(
            label="(=) Receita Bruta de Vendas",
            amount=receita_bruta_de_vendas,
            tone="highlight",
            formula="(Receita Bruta de Vendas e Serviços + Custos Mercadorias Vendidas)",
            component=_ROW_COMPONENT_RECEITA_BRUTA_DE_VENDAS,
            detail_kind="components",
            details=details.get(_ROW_COMPONENT_RECEITA_BRUTA_DE_VENDAS, []),
        ),
        _build_row(
            label="Receitas Financeiras",
            amount=receitas_financeiras,
            tone="positive",
            component=_ROW_COMPONENT_RECEITAS_FINANCEIRAS,
            detail_kind="financial_entries",
            is_expandable=True,
            details=details.get(_ROW_COMPONENT_RECEITAS_FINANCEIRAS, []),
        ),
        _build_row(
            label="Despesas Financeiras",
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
            formula="(Receita Bruta de Vendas + Receitas Financeiras + Despesas Financeiras)",
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
    all_components = {str(component) for component in _SOURCE_ROW_COMPONENTS}
    if not selected_financial_groups:
        return all_components

    visible_components: set[str] = set()

    for group in selected_financial_groups:
        current_group = group
        while current_group is not None:
            if current_group.dre_type:
                visible_components.add(current_group.dre_type)
                break
            current_group = current_group.parent

    # Always show all components in DRE to keep the structure intact, 
    # but the filter above will limit which items appear if needed,
    # wait actually the filter is to see what to sum. If we return only visible_components,
    # the unselected parts will be zeroed out.
    return visible_components


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(character for character in normalized if not unicodedata.combining(character)).casefold().strip()


def _build_row_details(
    *,
    movements_by_topic: dict[str, list[FinancialMovement]],
    visible_components: set[str],
    include_workshop_reference: bool,
) -> dict[str, list[dict[str, object]]]:
    details: dict[str, list[dict[str, object]]] = {}

    for component in _SOURCE_ROW_COMPONENTS:
        if component not in visible_components:
            continue
        topic_movements = movements_by_topic.get(component, [])
        if not topic_movements:
            continue
        details[component] = [_build_financial_movement_detail(movement=movement, include_workshop_reference=include_workshop_reference) for movement in topic_movements]

    return details


def _build_financial_movement_detail(*, movement: FinancialMovement, include_workshop_reference: bool) -> dict[str, object]:
    description = str(getattr(movement, "description", "") or "").strip()

    if description:
        summary = description
    else:
        source = getattr(movement, "source", None)
        summary = str(source.name) if source is not None else "-"

    reference_parts: list[str] = []

    if include_workshop_reference:
        workshop = getattr(movement, "workshop", None)
        workshop_name = getattr(workshop, "name", None)

        if workshop_name:
            reference_parts.append(f"Filial: {workshop_name}")

    source = getattr(movement, "source", None)
    source_name = getattr(source, "name", None)

    if source_name:
        reference_parts.append(f"Origem: {source_name}")

    nf_number = str(getattr(movement, "nf_number", "") or "").strip()

    if nf_number:
        reference_parts.append(f"NF: {nf_number}")

    payment_method = getattr(movement, "payment_method", None)

    if payment_method is not None:
        reference_parts.append(f"Pagamento: {payment_method}")

    if movement.due_date is not None:
        payment_date = movement.due_date
    else:
        workorder = getattr(movement, "workorder", None)
        workorder_created_at = getattr(workorder, "criado_em", None)

        if workorder_created_at is not None:
            payment_date = workorder_created_at.date()
        else:
            created_at = getattr(movement, "criado_em", None)
            payment_date = created_at.date() if created_at is not None else None

    created_at = getattr(movement, "criado_em", None)

    return {
        "movement": movement,
        "summary": summary,
        "reference": " | ".join(reference_parts) or "-",
        "entry_date": created_at.date() if created_at is not None else None,
        "payment_date": payment_date,
        "amount": movement.amount,
    }


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
