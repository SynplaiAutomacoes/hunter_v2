from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import unicodedata
from typing import Any, Sequence

from djmoney.money import Money

from apps.finance.models import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.workshops.models.workshops import Workshop


_ZERO_MONEY = Money("0.00", "BRL")


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
_SOURCE_ROW_COMPONENTS = (
    _ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS,
    _ROW_COMPONENT_CUSTOS_MERCADORIAS_VENDIDAS,
    _ROW_COMPONENT_RECEITAS_FINANCEIRAS,
    _ROW_COMPONENT_DESPESAS_FINANCEIRAS,
)
_VALID_TIPO_DATA_VALUES = {"PG", "NPG", "A"}


def build_dre_calculation(
    *,
    workshops: Sequence[Workshop],
    start_date: date | None,
    end_date: date | None,
    tipo_data: str = "A",
    selected_financial_groups: list[FinancialGroup] | None = None,
) -> DreCalculationResult:
    if not workshops or start_date is None or end_date is None or start_date > end_date:
        return DreCalculationResult(rows=_build_rows(), summary_cards=_build_summary_cards())

    financial_movements = _get_financial_movements(
        workshops=workshops,
        start_date=start_date,
        end_date=end_date,
        tipo_data=_normalize_tipo_data(tipo_data),
    )
    movements_by_topic = _group_financial_movements_by_topic(financial_movements=financial_movements)
    all_amounts = {component: _sum_movement_amounts(movements_by_topic.get(component, [])) for component in _SOURCE_ROW_COMPONENTS}

    visible_components = _resolve_visible_components(selected_financial_groups=selected_financial_groups)
    visible_amounts = {key: amount if key in visible_components else _ZERO_MONEY for key, amount in all_amounts.items()}
    receita_bruta_de_vendas = visible_amounts[_ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS] - visible_amounts[_ROW_COMPONENT_CUSTOS_MERCADORIAS_VENDIDAS]
    resultado_operacional = visible_amounts[_ROW_COMPONENT_RECEITAS_FINANCEIRAS] - visible_amounts[_ROW_COMPONENT_DESPESAS_FINANCEIRAS]
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


def _normalize_tipo_data(tipo_data: str | None) -> str:
    normalized_tipo_data = str(tipo_data or "A").strip().upper() or "A"
    if normalized_tipo_data not in _VALID_TIPO_DATA_VALUES:
        return "A"
    return normalized_tipo_data


def _get_financial_movements(*, workshops: Sequence[Workshop], start_date: date, end_date: date, tipo_data: str) -> list[FinancialMovement]:
    queryset = FinancialMovement.objects.filter(
        workshop__in=workshops,
        due_date__gte=start_date,
        due_date__lte=end_date,
    )

    if tipo_data == "PG":
        queryset = queryset.filter(is_paid=True)
    elif tipo_data == "NPG":
        queryset = queryset.filter(is_paid=False)

    return list(queryset.select_related("payment_method", "source", "workshop").order_by("due_date", "pk"))


def _group_financial_movements_by_topic(*, financial_movements: list[FinancialMovement]) -> dict[str, list[FinancialMovement]]:
    grouped_movements: dict[str, list[FinancialMovement]] = {component: [] for component in _SOURCE_ROW_COMPONENTS}
    return grouped_movements


def _sum_movement_amounts(movements: list[FinancialMovement]) -> Money:
    total = _ZERO_MONEY
    for movement in movements:
        amount = getattr(movement, "amount", None)
        if isinstance(amount, Money):
            total += amount
    return total


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
            detail_kind="financial_entries",
            is_expandable=True,
            details=details.get(_ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS, []),
        ),
        _build_row(
            label="(-) Custos Mercadorias Vendidas",
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
    all_components = {str(component) for component in _SOURCE_ROW_COMPONENTS}
    if not selected_financial_groups:
        return all_components

    selected_names = {_normalize_label(group.name) for group in selected_financial_groups}
    visible_components: set[str] = set()

    if {"receitas", "receitas de servicos", "receitas de pecas", "receita bruta de vendas e servicos", "receita bruta de vendas e serviços"} & selected_names:
        visible_components.add(_ROW_COMPONENT_RECEITA_BRUTA_VENDAS_E_SERVICOS)
    if {"custos", "custos de pecas", "custos de servicos", "custos mercadorias vendidas"} & selected_names:
        visible_components.add(_ROW_COMPONENT_CUSTOS_MERCADORIAS_VENDIDAS)
    if {"receitas financeiras", "receitas outras", "receitas"} & selected_names:
        visible_components.add(_ROW_COMPONENT_RECEITAS_FINANCEIRAS)
    if {"despesas", "despesas financeiras"} & selected_names:
        visible_components.add(_ROW_COMPONENT_DESPESAS_FINANCEIRAS)

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
    created_at = getattr(movement, "criado_em", None)
    return {
        "summary": _build_financial_movement_summary(movement=movement),
        "reference": _build_financial_movement_reference(movement=movement, include_workshop_reference=include_workshop_reference),
        "entry_date": created_at.date() if created_at is not None else None,
        "payment_date": movement.due_date,
        "amount": movement.amount,
    }


def _build_financial_movement_summary(*, movement: FinancialMovement) -> str:
    description = str(getattr(movement, "description", "") or "").strip()
    if description:
        return description

    source = getattr(movement, "source", None)
    if source is not None:
        return str(source.name)

    return "-"


def _build_financial_movement_reference(*, movement: FinancialMovement, include_workshop_reference: bool) -> str:
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

    return " | ".join(reference_parts) or "-"


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
