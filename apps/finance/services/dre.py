from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from djmoney.money import Money
from django.db.models import Q

from apps.finance.models import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.workorder.models import WorkOrderPaymentMethod, WorkOrder
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
        selected_financial_groups=selected_financial_groups,
    )

    # --- Monta detalhes de cada seção ---
    def details(mvs: list[FinancialMovement]) -> list[dict]:
        return [_build_detail(m, include_workshop_ref) for m in mvs]

    def workorder_payment_method_details(payments: list[WorkOrderPaymentMethod]) -> list[dict]:
        return [_build_wo_pm_detail(p, include_workshop_ref) for p in payments]

    def maquininha_tax_details(mvs: list[FinancialMovement]) -> list[dict]:
        return [_build_maquininha_detail(m, include_workshop_ref) for m in mvs]

    def workorder_cost_details(wos: list[WorkOrder]) -> list[dict]:
        return [_build_workorder_cost_detail(wo, include_workshop_ref) for wo in wos]

    # Receita Bruta de Vendas e Serviços
    pagamentos_ordens_de_servico = (
        WorkOrderPaymentMethod.objects.filter(workorder__workshop__in=workshops)
        .select_related("workorder", "workorder__budget", "workorder__budget__customer")
        .prefetch_related(
            "workorder__items__product",
            "workorder__items__service",
            "workorder__items__kit",
            "workorder__items__kit_overrides",
            "workorder__items__kit__kit_products__product",
            "workorder__items__kit__kit_services__service",
        )
    )
    if start_date is not None:
        pagamentos_ordens_de_servico = pagamentos_ordens_de_servico.filter(due_date__gte=start_date)
    if end_date is not None:
        pagamentos_ordens_de_servico = pagamentos_ordens_de_servico.filter(due_date__lte=end_date)

    total_receita_bruta_de_vendas_e_servicos = sum((payment.total_paid for payment in pagamentos_ordens_de_servico), _ZERO)
    detail_receita_bruta_de_vendas_e_servicos = workorder_payment_method_details(list(pagamentos_ordens_de_servico))
    # ----------------------------------

    # Custo Mercadorias Vendidas
    taxa_maquininha_os = FinancialMovement.objects.filter(workorder_payment__in=pagamentos_ordens_de_servico, description="Pagamento da taxa da maquininha").select_related("workorder_payment", "workorder_payment__workorder")
    total_taxa_maquininha_os = _sum_movements(list(taxa_maquininha_os))

    workorders = set(payment.workorder for payment in pagamentos_ordens_de_servico if payment.workorder)
    total_custos_os = sum((wo.total_costs_products_value for wo in workorders), _ZERO)

    total_custos_mercadorias_vendidas = total_taxa_maquininha_os + total_custos_os
    detail_custos_mercadorias_vendidas = maquininha_tax_details(list(taxa_maquininha_os)) + workorder_cost_details(list(workorders))
    # --------------------------

    # Receita Bruta de Vendas
    total_receita_bruta_de_vendas = total_receita_bruta_de_vendas_e_servicos - total_custos_mercadorias_vendidas
    # -----------------------

    # Receitas Financeiras
    fin_revenue_mvs = [m for m in movements if m.workorder is None and m.direction == FinancialMovement.MovementDirection.CREDIT]
    total_receitas_financeiras = _sum_movements(fin_revenue_mvs)
    detail_receitas_financeiras = details(fin_revenue_mvs)
    # -------------------

    # Despesas Financeiras
    fin_expense_mvs = [m for m in movements if m.workorder is None and m.direction == FinancialMovement.MovementDirection.DEBIT]
    total_despesas_financeiras = _sum_movements(fin_expense_mvs)
    detail_despesas_financeiras = details(fin_expense_mvs)
    # --------------------

    # Resultado Operacional
    total_resultado_operacional = total_receitas_financeiras - total_despesas_financeiras
    # ---------------------

    rows = [
        _row(
            label="Receita Bruta de Vendas e Serviços",
            amount=total_receita_bruta_de_vendas_e_servicos,
            tone="positive",
            component=COMP_GROSS_REVENUE,
            detail_kind="financial_entries",
            is_expandable=True,
            details=detail_receita_bruta_de_vendas_e_servicos,
        ),
        _row(
            label="Custos Mercadorias Vendidas",
            amount=total_custos_mercadorias_vendidas,
            tone="negative",
            component=COMP_COGS,
            detail_kind="financial_entries",
            is_expandable=True,
            details=detail_custos_mercadorias_vendidas,
        ),
        _row(
            label="(=) Receita Líquida",
            amount=total_receita_bruta_de_vendas,
            tone="highlight",
            component=COMP_GROSS_PROFIT,
            formula="Receita Bruta de Vendas e Serviços - Custos Mercadorias Vendidas",
        ),
        _row(
            label="Receitas Financeiras",
            amount=total_receitas_financeiras,
            tone="positive",
            component=COMP_FINANCIAL_REVENUE,
            detail_kind="financial_entries",
            is_expandable=True,
            details=detail_receitas_financeiras,
        ),
        _row(
            label="Despesas Financeiras",
            amount=total_despesas_financeiras,
            tone="negative",
            component=COMP_FINANCIAL_EXPENSE,
            detail_kind="financial_entries",
            is_expandable=True,
            details=detail_despesas_financeiras,
        ),
        _row(
            label="(=) Resultado Operacional",
            amount=total_resultado_operacional,
            tone="result",
            component=COMP_OPERATING_RESULT,
            formula="Receitas Financeiras - Despesas Financeiras",
        ),
    ]

    summary_cards = [
        {"label": "Receita Bruta de Vendas", "amount": total_receita_bruta_de_vendas, "accent": "text-sky-700"},
        {"label": "Resultado Operacional", "amount": total_resultado_operacional, "accent": "text-amber-700"},
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
        if m.workorder_id and m.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT:
            amount = getattr(m.workorder, "accounting_total_budget_value", _ZERO)
        else:
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


def _fetch_movements(*, workshops: Sequence[Workshop], start_date: date | None, end_date: date | None, tipo_data: str, selected_financial_groups: list[FinancialGroup] | None = None) -> list[FinancialMovement]:
    qs = FinancialMovement.objects.filter(workshop__in=workshops)

    if start_date is not None:
        qs = qs.filter(due_date__gte=start_date)
    if end_date is not None:
        qs = qs.filter(due_date__lte=end_date)

    if selected_financial_groups:
        budget_plan_ids = [g.pk for g in selected_financial_groups]
        qs = qs.filter(budget_plan_id__in=budget_plan_ids)

    qs = qs.filter(Q(movement_group__isnull=True) | Q(movement_kind=FinancialMovement.MovementKind.GROUP_PARENT))

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
        )
        .prefetch_related(
            "workorder__payments",
            "workorder__payments__payment_method",
        )
        .order_by("due_date", "criado_em", "pk")
    )


# ---------------------------------------------------------------------------
# Construtores de detalhe e linha
# ---------------------------------------------------------------------------


def _build_detail(m: FinancialMovement, include_workshop_ref: bool) -> dict:
    """Monta o dicionário de detalhe de uma movimentação para o template."""
    workorder = getattr(m, "workorder", None)
    budget = getattr(workorder, "budget", None)

    if m.workorder_id and m.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT:
        amount = getattr(workorder, "accounting_total_budget_value", _ZERO)
        summary = _agent_label(m)
        payments = list(workorder.payments.all()) if hasattr(workorder, "payments") else []
        payment_date = max((p.due_date for p in payments if p.due_date), default=m.due_date)
    else:
        amount = m.amount
        summary = str(m.description or "").strip() or _agent_label(m)
        payment_date = m.due_date

    reference_parts: list[str] = []
    if include_workshop_ref and m.workshop_id:
        reference_parts.append(f"Filial: {m.workshop.name}")
    if m.workorder_id:
        reference_parts.append(f"O.S #{getattr(budget, 'pk', workorder.pk if workorder else '-')}")
    if m.nf_number:
        reference_parts.append(f"NF: {m.nf_number}")

    if m.workorder_id and m.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT:
        payments = list(workorder.payments.all()) if hasattr(workorder, "payments") else []
        method_names = []
        for p in payments:
            desc = getattr(getattr(p, "payment_method", None), "description", None)
            if desc and desc not in method_names:
                method_names.append(str(desc))

        if method_names:
            pm_str = method_names[0] if len(method_names) == 1 else "Múltiplos"
            reference_parts.append(f"Pagamento: {pm_str}")
    elif m.payment_method_id:
        reference_parts.append(f"Pagamento: {m.payment_method}")

    created_at = getattr(m, "criado_em", None)

    workorder_id = None
    if m.workorder_id:
        workorder_id = m.workorder_id
    elif hasattr(m, "workorder_payment") and m.workorder_payment and m.workorder_payment.workorder_id:
        workorder_id = m.workorder_payment.workorder_id

    return {
        "movement": m,
        "workorder_id": workorder_id,
        "summary": summary,
        "reference": " | ".join(reference_parts) or "-",
        "entry_date": created_at.date() if created_at else None,
        "payment_date": payment_date,
        "amount": amount,
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


def _build_wo_pm_detail(payment: WorkOrderPaymentMethod, include_workshop_ref: bool) -> dict:
    workorder = payment.workorder
    budget = getattr(workorder, "budget", None)
    customer = getattr(budget, "customer", None)
    pk = getattr(budget, "pk", "-")
    name = getattr(customer, "name", "-") or "-"

    summary = f"O.S #{pk} - {name}"
    payment_method_name = getattr(getattr(payment, "payment_method", None), "description", "-") or "-"
    reference = f"Pagamento: {payment_method_name}"

    if include_workshop_ref and workorder and workorder.workshop_id:
        reference = f"Filial: {workorder.workshop.name} | {reference}"

    return {
        "movement": None,
        "workorder_id": workorder.pk if workorder else None,
        "summary": summary,
        "reference": reference,
        "entry_date": getattr(payment, "criado_em", None),
        "payment_date": payment.due_date,
        "amount": payment.total_paid,
    }


def _build_maquininha_detail(m: FinancialMovement, include_workshop_ref: bool) -> dict:
    return _build_detail(m, include_workshop_ref)


def _build_workorder_cost_detail(wo: WorkOrder, include_workshop_ref: bool) -> dict:
    budget = getattr(wo, "budget", None)
    customer = getattr(budget, "customer", None)
    pk = getattr(budget, "pk", "-")
    name = getattr(customer, "name", "-") or "-"

    summary = f"Custo - O.S #{pk} - {name}"
    reference = f"O.S #{pk}"

    if include_workshop_ref and wo.workshop_id:
        reference = f"Filial: {wo.workshop.name} | {reference}"

    return {
        "movement": None,
        "workorder_id": wo.pk,
        "summary": summary,
        "reference": reference,
        "entry_date": getattr(wo, "criado_em", None),
        "payment_date": getattr(wo, "criado_em", None),
        "amount": wo.total_costs_products_value,
    }


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
            _row(label="Receita Bruta de Vendas e Serviços", amount=_ZERO, tone="positive", component=COMP_GROSS_REVENUE, detail_kind="financial_entries", is_expandable=True),
            _row(label="Custos Mercadorias Vendidas", amount=_ZERO, tone="negative", component=COMP_COGS, detail_kind="financial_entries", is_expandable=True),
            _row(label="(=) Receita Bruta de Vendas", amount=_ZERO, tone="highlight", component=COMP_GROSS_PROFIT, formula="Receita Bruta de Vendas e Serviços + Custos Mercadorias Vendidas"),
            _row(label="Receitas Financeiras", amount=_ZERO, tone="positive", component=COMP_FINANCIAL_REVENUE, detail_kind="financial_entries", is_expandable=True),
            _row(label="Despesas Financeiras", amount=_ZERO, tone="negative", component=COMP_FINANCIAL_EXPENSE, detail_kind="financial_entries", is_expandable=True),
            _row(label="(=) Resultado Operacional", amount=_ZERO, tone="result", component=COMP_OPERATING_RESULT, formula="Receita Bruta de Vendas + Receitas Financeiras + Despesas Financeiras"),
        ],
        summary_cards=[
            {"label": "Receita Bruta de Vendas", "amount": _ZERO, "accent": "text-sky-700"},
            {"label": "Resultado Operacional", "amount": _ZERO, "accent": "text-amber-700"},
        ],
    )


def _normalize_tipo_data(value: str) -> str:
    normalized = str(value or "A").strip().upper()
    return normalized if normalized in _VALID_TIPO_DATA else "A"
