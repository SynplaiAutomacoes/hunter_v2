from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
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
COMP_GROSS_REVENUE = "receita_bruta_vendas_e_servicos"
COMP_COGS = "custos_mercadorias_vendidas"
COMP_GROSS_PROFIT = "receita_bruta_de_vendas"
COMP_FINANCIAL_REVENUE = "receitas_financeiras"
COMP_FINANCIAL_EXPENSE = "despesas_financeiras"
COMP_OPERATING_RESULT = "resultado_operacional"

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
    financial_groups = list(FinancialGroup.objects.filter(workshop__in=workshops).select_related("parent").order_by("sort_key", "id"))
    financial_groups = _filter_financial_groups_by_selection(
        financial_groups=financial_groups,
        selected_financial_groups=selected_financial_groups or [],
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
    fin_revenue_groups, total_receitas_financeiras = _build_financial_group_tree(
        movements=movements,
        direction=FinancialMovement.MovementDirection.CREDIT,
        financial_groups=financial_groups,
    )
    detail_receitas_financeiras = fin_revenue_groups
    # -------------------

    # Despesas Financeiras
    fin_expense_groups, total_despesas_financeiras = _build_financial_group_tree(
        movements=movements,
        direction=FinancialMovement.MovementDirection.DEBIT,
        financial_groups=financial_groups,
    )
    detail_despesas_financeiras = fin_expense_groups
    # --------------------

    # Resultado Operacional
    total_resultado_operacional = _calculate_operating_result(
        financial_revenue=total_receitas_financeiras,
        financial_expense=total_despesas_financeiras,
    )
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
            detail_kind="group_entries",
            is_expandable=True,
            details=detail_receitas_financeiras,
        ),
        _row(
            label="Despesas Financeiras",
            amount=total_despesas_financeiras,
            tone="negative",
            component=COMP_FINANCIAL_EXPENSE,
            detail_kind="group_entries",
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
        {"label": "Receita Líquida", "amount": total_receita_bruta_de_vendas, "accent": "text-sky-700"},
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
            amount = getattr(m.workorder, "total_budget_value", _ZERO)
        else:
            amount = m.amount

        if not isinstance(amount, Money):
            continue
        if m.direction == FinancialMovement.MovementDirection.DEBIT:
            total -= amount
        else:
            total += amount
    return total


def _sum_detail_amounts(details: list[dict]) -> Money:
    total = _ZERO
    for detail in details:
        amount = detail.get("amount", _ZERO)
        if isinstance(amount, Money):
            total += amount
    return total


def _calculate_operating_result(*, financial_revenue: Money, financial_expense: Money) -> Money:
    expense_amount = getattr(financial_expense, "amount", Decimal("0.00"))
    if expense_amount >= Decimal("0.00"):
        return financial_revenue - financial_expense
    return financial_revenue + financial_expense


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
        amount = getattr(workorder, "total_budget_value", _ZERO)
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
    if m.source_id:
        reference_parts.append(f"Origem: {m.source.name}")
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
        "budget_plan": getattr(m, "budget_plan", None),
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
        "budget_plan": None,
    }


def _build_financial_group_rollup(*, movements: list[FinancialMovement], direction: str, financial_groups: list[FinancialGroup]) -> list[dict]:
    grouped: dict[int, dict] = {}
    groups_by_id = {group.pk: group for group in financial_groups}
    relevant_group_ids: set[int] = set()

    for movement in movements:
        if movement.workorder_id is not None or movement.direction != direction:
            continue
        group = getattr(movement, "budget_plan", None)
        group_id = getattr(group, "pk", None)
        while group_id:
            relevant_group_ids.add(group_id)
            parent_id = getattr(groups_by_id.get(group_id), "parent_id", None)
            group_id = parent_id

    for group in financial_groups:
        if group.pk not in relevant_group_ids:
            continue
        group_id = group.pk
        grouped[group_id] = {
            "group": group,
            "amount": _ZERO,
            "details": [],
        }

    for movement in movements:
        if movement.workorder_id is not None:
            continue
        if movement.direction != direction:
            continue

        detail = _build_detail(movement, include_workshop_ref=False)
        group = detail.get("budget_plan") or getattr(movement, "budget_plan", None)
        if group is None or not getattr(group, "pk", None):
            continue

        group_id = group.pk
        if group_id not in grouped:
            grouped[group_id] = {
                "group": group,
                "amount": _ZERO,
                "details": [],
            }

        grouped[group_id]["details"].append(detail)

    ordered_groups = []
    for payload in grouped.values():
        payload["amount"] = _sum_detail_amounts(payload["details"])
        ordered_groups.append(payload)

    ordered_groups.sort(key=lambda item: (getattr(item["group"], "sort_key", ""), getattr(item["group"], "pk", 0)))

    return ordered_groups


def _build_financial_group_tree(*, movements: list[FinancialMovement], direction: str, financial_groups: list[FinancialGroup]) -> tuple[list[dict], Money]:
    grouped = _build_financial_group_rollup(movements=movements, direction=direction, financial_groups=financial_groups)
    nodes = _build_group_tree(groups=grouped)
    roots = _build_group_tree_roots(nodes=nodes)
    total = sum((root["amount"] for root in roots), _ZERO)
    return roots, total


def _build_group_tree(*, groups: list[dict]) -> dict[int, dict]:
    nodes: dict[int, dict] = {}

    for group_payload in groups:
        group = group_payload["group"]
        group_id = group.pk
        nodes[group_id] = {
            "group": group,
            "direct_amount": group_payload["amount"],
            "amount": group_payload["amount"],
            "details": group_payload["details"],
            "children": [],
        }

    for node in list(nodes.values()):
        parent_id = getattr(node["group"], "parent_id", None)
        if parent_id and parent_id in nodes:
            nodes[parent_id]["children"].append(node)

    for node in list(nodes.values()):
        node["children"].sort(key=lambda child: (getattr(child["group"], "sort_key", ""), getattr(child["group"], "pk", 0)))

    for node in sorted(nodes.values(), key=lambda item: getattr(item["group"], "level", 0), reverse=True):
        for child in node["children"]:
            node["amount"] += child["amount"]

    return nodes


def _build_group_tree_roots(*, nodes: dict[int, dict]) -> list[dict]:
    roots = [node for node in nodes.values() if not getattr(node["group"], "parent_id", None)]
    roots.sort(key=lambda node: (getattr(node["group"], "sort_key", ""), getattr(node["group"], "pk", 0)))
    return roots


def _flatten_financial_group_details(groups: list[dict]) -> list[dict]:
    if not groups:
        return []

    nodes = _build_group_tree(groups=groups)
    roots = _build_group_tree_roots(nodes=nodes)
    flattened: list[dict] = []

    def walk(node: dict, depth: int) -> None:
        flattened.append(
            {
                "kind": "group",
                "depth": depth,
                "group": node["group"],
                "amount": node["amount"],
                "children_count": len(node["children"]),
            }
        )

        for detail in node["details"]:
            flattened.append(
                {
                    "kind": "movement",
                    "depth": depth + 1,
                    "detail": detail,
                }
            )

        for child in node["children"]:
            walk(child, depth + 1)

    for root in roots:
        walk(root, 0)

    return flattened


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
            _row(label="Receitas Financeiras", amount=_ZERO, tone="positive", component=COMP_FINANCIAL_REVENUE, detail_kind="group_entries", is_expandable=True),
            _row(label="Despesas Financeiras", amount=_ZERO, tone="negative", component=COMP_FINANCIAL_EXPENSE, detail_kind="group_entries", is_expandable=True),
            _row(label="(=) Resultado Operacional", amount=_ZERO, tone="result", component=COMP_OPERATING_RESULT, formula="Receita Bruta de Vendas + Receitas Financeiras + Despesas Financeiras"),
        ],
        summary_cards=[
            {"label": "Receita Líquida", "amount": _ZERO, "accent": "text-sky-700"},
            {"label": "Resultado Operacional", "amount": _ZERO, "accent": "text-amber-700"},
        ],
    )


def _normalize_tipo_data(value: str) -> str:
    normalized = str(value or "A").strip().upper()
    return normalized if normalized in _VALID_TIPO_DATA else "A"


def _filter_financial_groups_by_selection(*, financial_groups: list[FinancialGroup], selected_financial_groups: list[FinancialGroup]) -> list[FinancialGroup]:
    if not selected_financial_groups:
        return financial_groups

    selected_ids = {group.pk for group in selected_financial_groups}
    parent_map = {group.pk: group.parent_id for group in financial_groups}
    allowed_ids = set(selected_ids)

    for group_id in list(selected_ids):
        parent_id = parent_map.get(group_id)
        while parent_id:
            allowed_ids.add(parent_id)
            parent_id = parent_map.get(parent_id)

    return [group for group in financial_groups if group.pk in allowed_ids]
