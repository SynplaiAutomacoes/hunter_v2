from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from djmoney.money import Money

from apps.finance.models import FinancialGroup
from apps.finance.models.financial_group import DreType
from apps.finance.models.financial_movement import FinancialMovement
from apps.workshops.models.workshops import Workshop


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_ZERO = Money("0.00", "BRL")

# Chaves de componente usadas no template (row.component)
COMP_GROSS_REVENUE = "gross_revenue"
COMP_COGS = "cogs"
COMP_GROSS_PROFIT = "gross_profit"
COMP_FINANCIAL_REVENUE = "financial_revenue"
COMP_FINANCIAL_EXPENSE = "financial_expense"
COMP_OPERATING_RESULT = "operating_result"

_VALID_TIPO_DATA = {"PG", "NPG", "A"}


# ---------------------------------------------------------------------------
# Resultado público
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DreCalculationResult:
    rows: list[dict]
    summary_cards: list[dict]


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

def build_dre_calculation(
    *,
    workshops: Sequence[Workshop],
    start_date: date | None,
    end_date: date | None,
    tipo_data: str = "A",
    selected_financial_groups: list[FinancialGroup] | None = None,
) -> DreCalculationResult:
    """Calcula a DRE e retorna as linhas e cards de resumo."""

    if not workshops or start_date is None or end_date is None or start_date > end_date:
        return _empty_result()

    tipo_data = _normalize_tipo_data(tipo_data)
    include_workshop_ref = len(list(workshops)) > 1

    movements = _fetch_movements(
        workshops=workshops,
        start_date=start_date,
        end_date=end_date,
        tipo_data=tipo_data,
    )

    # --- Classifica movimentações por seção ---
    gross_revenue_mvs  = [m for m in movements if m.workorder_id is not None]
    cogs_mvs           = [m for m in movements if m.workorder_id is None and _resolve_dre_type(m) == DreType.COGS]
    fin_revenue_mvs    = [m for m in movements if m.workorder_id is None and _resolve_dre_type(m) == DreType.FINANCIAL_REVENUE]
    fin_expense_mvs    = [m for m in movements if m.workorder_id is None and _resolve_dre_type(m) == DreType.FINANCIAL_EXPENSE]
    print(f"gross_revenue_mvs: {gross_revenue_mvs}")
    print(f"cogs_mvs: {cogs_mvs}")
    print(f"fin_revenue_mvs: {fin_revenue_mvs}")
    print(f"fin_expense_mvs: {fin_expense_mvs}")

    # --- Calcula totais ---
    gross_revenue  = _sum_movements(gross_revenue_mvs)
    cogs           = _sum_movements(cogs_mvs)
    gross_profit   = gross_revenue + cogs          # cogs já vem negativo (DEBIT)
    fin_revenue    = _sum_movements(fin_revenue_mvs)
    fin_expense    = _sum_movements(fin_expense_mvs)
    op_result      = gross_profit + fin_revenue + fin_expense

    # --- Monta detalhes de cada seção ---
    def details(mvs: list[FinancialMovement]) -> list[dict]:
        return [_build_detail(m, include_workshop_ref) for m in mvs]

    rows = [
        _row(
            label="Receita Bruta de Vendas e Serviços",
            amount=gross_revenue,
            tone="positive",
            component=COMP_GROSS_REVENUE,
            detail_kind="financial_entries",
            is_expandable=True,
            details=details(gross_revenue_mvs),
        ),
        _row(
            label="Custos Mercadorias Vendidas",
            amount=cogs,
            tone="negative",
            component=COMP_COGS,
            detail_kind="financial_entries",
            is_expandable=True,
            details=details(cogs_mvs),
        ),
        _row(
            label="(=) Receita Bruta de Vendas",
            amount=gross_profit,
            tone="highlight",
            component=COMP_GROSS_PROFIT,
            formula="Receita Bruta de Vendas e Serviços + Custos Mercadorias Vendidas",
        ),
        _row(
            label="Receitas Financeiras",
            amount=fin_revenue,
            tone="positive",
            component=COMP_FINANCIAL_REVENUE,
            detail_kind="financial_entries",
            is_expandable=True,
            details=details(fin_revenue_mvs),
        ),
        _row(
            label="Despesas Financeiras",
            amount=fin_expense,
            tone="negative",
            component=COMP_FINANCIAL_EXPENSE,
            detail_kind="financial_entries",
            is_expandable=True,
            details=details(fin_expense_mvs),
        ),
        _row(
            label="(=) Resultado Operacional",
            amount=op_result,
            tone="result",
            component=COMP_OPERATING_RESULT,
            formula="Receita Bruta de Vendas + Receitas Financeiras + Despesas Financeiras",
        ),
    ]

    summary_cards = [
        {"label": "Receita Bruta de Vendas", "amount": gross_profit, "accent": "text-sky-700"},
        {"label": "Resultado Operacional",   "amount": op_result,    "accent": "text-amber-700"},
    ]

    return DreCalculationResult(rows=rows, summary_cards=summary_cards)

# ---------------------------------------------------------------------------

def _resolve_dre_type(m: FinancialMovement) -> str | None:
    """Sobe na hierarquia do budget_plan até encontrar um dre_type."""
    group = getattr(m, "budget_plan", None)
    while group is not None:
        if group.dre_type:
            return group.dre_type
        group = group.parent if group.parent_id else None
    return None


# ---------------------------------------------------------------------------
# Cálculo monetário
# ---------------------------------------------------------------------------

def _sum_movements(movements: list[FinancialMovement]) -> Money:
    """Soma amounts respeitando a direção (CREDIT soma, DEBIT subtrai)."""
    total = _ZERO
    for m in movements:
        amount = m.amount
        if not isinstance(amount, Money):
            continue
        if m.direction == FinancialMovement.MovementDirection.DEBIT:
            total -= amount
        else:
            total += amount
    return total


# ---------------------------------------------------------------------------
# Busca de movimentações
# ---------------------------------------------------------------------------

def _fetch_movements(*, workshops: Sequence[Workshop], start_date: date, end_date: date, tipo_data: str) -> list[FinancialMovement]:
    qs = FinancialMovement.objects.filter(
        workshop__in=workshops,
        due_date__gte=start_date,
        due_date__lte=end_date,
    )

    for i in qs:
        print(f"i: {i} | budget_plan: {i.budget_plan if i.budget_plan else None} | dre_type: {i.budget_plan.dre_type if i.budget_plan and i.budget_plan.dre_type else None}")

    if tipo_data == "PG":
        qs = qs.filter(is_paid=True)
    elif tipo_data == "NPG":
        qs = qs.filter(is_paid=False)

    return list(
        qs.select_related(
            "payment_method",
            "source",
            "workshop",
            "workorder",
            "workorder__budget",
            "workorder__budget__customer",
            "budget_plan",
            "budget_plan__parent",
            "budget_plan__parent__parent",
        ).order_by("due_date", "criado_em", "pk")
    )


# ---------------------------------------------------------------------------
# Construtores de detalhe e linha
# ---------------------------------------------------------------------------

def _build_detail(m: FinancialMovement, include_workshop_ref: bool) -> dict:
    """Monta o dicionário de detalhe de uma movimentação para o template."""
    summary = str(m.description or "").strip() or _agent_label(m)

    reference_parts: list[str] = []
    if include_workshop_ref and m.workshop_id:
        reference_parts.append(f"Filial: {m.workshop.name}")
    if m.source_id:
        reference_parts.append(f"Origem: {m.source.name}")
    if m.nf_number:
        reference_parts.append(f"NF: {m.nf_number}")
    if m.payment_method_id:
        reference_parts.append(f"Pagamento: {m.payment_method}")

    created_at = getattr(m, "criado_em", None)

    return {
        "movement": m,
        "summary": summary,
        "reference": " | ".join(reference_parts) or "-",
        "entry_date": created_at.date() if created_at else None,
        "payment_date": m.due_date,
        "amount": m.amount,
    }


def _agent_label(m: FinancialMovement) -> str:
    if m.workorder_id:
        budget = getattr(getattr(m, "workorder", None), "budget", None)
        customer = getattr(budget, "customer", None)
        pk = getattr(budget, "pk", "-")
        name = getattr(customer, "name", "-") or "-"
        return f"O.S #{pk} - {name}"
    if m.collaborator_id:
        return str(m.collaborator.name)
    if m.supplier_id:
        return str(m.supplier.name)
    if m.source_id:
        return str(m.source.name)
    return "-"


def _row(
    *,
    label: str,
    amount: Money,
    tone: str,
    component: str,
    detail_kind: str = "components",
    formula: str | None = None,
    is_expandable: bool = False,
    details: list[dict] | None = None,
) -> dict:
    return {
        "label": label,
        "amount": amount,
        "tone": tone,
        "component": component,
        "detail_kind": detail_kind,
        "formula": formula,
        "is_expandable": is_expandable,
        "details": details or [],
    }


def _empty_result() -> DreCalculationResult:
    return DreCalculationResult(
        rows=[
            _row(label="Receita Bruta de Vendas e Serviços", amount=_ZERO, tone="positive",  component=COMP_GROSS_REVENUE,     detail_kind="financial_entries", is_expandable=True),
            _row(label="Custos Mercadorias Vendidas",         amount=_ZERO, tone="negative",  component=COMP_COGS,              detail_kind="financial_entries", is_expandable=True),
            _row(label="(=) Receita Bruta de Vendas",         amount=_ZERO, tone="highlight", component=COMP_GROSS_PROFIT,      formula="Receita Bruta de Vendas e Serviços + Custos Mercadorias Vendidas"),
            _row(label="Receitas Financeiras",                amount=_ZERO, tone="positive",  component=COMP_FINANCIAL_REVENUE, detail_kind="financial_entries", is_expandable=True),
            _row(label="Despesas Financeiras",                amount=_ZERO, tone="negative",  component=COMP_FINANCIAL_EXPENSE, detail_kind="financial_entries", is_expandable=True),
            _row(label="(=) Resultado Operacional",           amount=_ZERO, tone="result",    component=COMP_OPERATING_RESULT,  formula="Receita Bruta de Vendas + Receitas Financeiras + Despesas Financeiras"),
        ],
        summary_cards=[
            {"label": "Receita Bruta de Vendas", "amount": _ZERO, "accent": "text-sky-700"},
            {"label": "Resultado Operacional",   "amount": _ZERO, "accent": "text-amber-700"},
        ],
    )


def _normalize_tipo_data(value: str) -> str:
    normalized = str(value or "A").strip().upper()
    return normalized if normalized in _VALID_TIPO_DATA else "A"
