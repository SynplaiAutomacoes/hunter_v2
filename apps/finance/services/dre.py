from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import logging
import json
from typing import Sequence

from djmoney.money import Money
from django.db.models import Q

from apps.finance.models import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_ZERO = Money("0.00", "BRL")

# Chaves de componente usadas no template (row.component)
COMP_GROSS_REVENUE = "receita_bruta_vendas_e_servicos"
COMP_COGS = "custos_mercadorias_vendidas"
COMP_COS = "custos_servicos_vendidos"
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


@dataclass(frozen=True)
class _StaticDreGroup:
    pk: int
    name: str
    sort_key: str = ""


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
        return [_build_maquininha_detail(m, include_workshop_ref, budget_plan=cost_budget_plan) for m in mvs]

    cost_budget_plan = _resolve_default_sales_group(financial_groups=financial_groups)

    def workorder_cost_details(wos: list[WorkOrder]) -> list[dict]:
        return [_build_workorder_cost_detail(wo, include_workshop_ref, budget_plan=cost_budget_plan) for wo in wos]

    # Receita Bruta de Vendas e Serviços
    pagamentos_ordens_de_servico = (
        WorkOrderPaymentMethod.objects.filter(
            workorder__workshop__in=workshops,
            workorder__budget_type="sale",
            workorder__status__in=(WorkOrderStatus.APPROVED, WorkOrderStatus.DRAFT),
        )
        .select_related("workorder", "workorder__budget", "workorder__budget__customer", "payment_method")
        .prefetch_related(
            "workorder__items__product",
            "workorder__items__service",
            "workorder__items__kit",
            "workorder__items__kit_overrides",
            "workorder__items__kit__kit_products__product",
            "workorder__items__kit__kit_services__service",
        )
        .order_by("criado_em", "pk")
    )
    if start_date is not None:
        pagamentos_ordens_de_servico = pagamentos_ordens_de_servico.filter(due_date__gte=start_date)
    if end_date is not None:
        pagamentos_ordens_de_servico = pagamentos_ordens_de_servico.filter(due_date__lte=end_date)

    pagamentos_ordens_de_servico = list(pagamentos_ordens_de_servico)
    total_receita_bruta_de_vendas_e_servicos = sum((payment.total_paid for payment in pagamentos_ordens_de_servico), _ZERO)
    detail_receita_bruta_de_vendas_e_servicos = workorder_payment_method_details(pagamentos_ordens_de_servico)
    workorder_payment_totals = _build_workorder_payment_totals(payments=pagamentos_ordens_de_servico)
    workorder_revenue_movements = _fetch_workorder_revenue_movements(
        workshops=workshops,
        workorder_ids=list(workorder_payment_totals.keys()),
        selected_financial_groups=selected_financial_groups,
    )
    logger.info(
        "DRE revenue payment inputs | %s",
        json.dumps(
            {
                "workshop_ids": [workshop.pk for workshop in workshops],
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "tipo_data": tipo_data,
                "selected_financial_group_ids": [group.pk for group in selected_financial_groups or []],
                "gross_revenue_total": str(total_receita_bruta_de_vendas_e_servicos),
                "workorder_payment_totals": {str(workorder_id): str(amount) for workorder_id, amount in workorder_payment_totals.items()},
                "payments": [
                    {
                        "payment_id": payment.pk,
                        "workorder_id": payment.workorder_id,
                        "budget_id": getattr(getattr(payment.workorder, "budget", None), "pk", None),
                        "due_date": payment.due_date.isoformat() if payment.due_date else None,
                        "total_paid": str(payment.total_paid),
                    }
                    for payment in pagamentos_ordens_de_servico
                ],
                "revenue_movements": [
                    {
                        "movement_id": movement.pk,
                        "workorder_id": getattr(movement, "workorder_id", None),
                        "budget_id": getattr(getattr(movement.workorder, "budget", None), "pk", None),
                        "movement_due_date": movement.due_date.isoformat() if movement.due_date else None,
                        "budget_plan_id": getattr(getattr(movement, "budget_plan", None), "pk", None),
                        "budget_plan_name": getattr(getattr(movement, "budget_plan", None), "name", None),
                        "resolved_amount": str(_resolve_workorder_revenue_amount(movement=movement, workorder_payment_totals=workorder_payment_totals)),
                    }
                    for movement in workorder_revenue_movements
                ],
            },
            ensure_ascii=True,
            default=str,
        ),
    )
    # ----------------------------------

    # Custos
    delivered_payment_ids = [payment.pk for payment in pagamentos_ordens_de_servico if payment.workorder.status == WorkOrderStatus.APPROVED and payment.workorder.delivered_at is not None]

    taxa_maquininha_os = FinancialMovement.objects.filter(workorder_payment_id__in=delivered_payment_ids, description="Pagamento da taxa da maquininha").select_related("workorder_payment", "workorder_payment__workorder")

    delivered_workorders_with_costs = _fetch_delivered_workorders_with_costs(payments=pagamentos_ordens_de_servico)
    delivered_workorders = [workorder for workorder, _ in delivered_workorders_with_costs]

    detail_taxas_maquininha = maquininha_tax_details(list(taxa_maquininha_os))
    detail_custos_pecas = _build_workorder_cost_component_details(
        workorders=delivered_workorders,
        include_workshop_ref=include_workshop_ref,
        budget_plan=cost_budget_plan,
        component_label="Custos de Peças",
        amount_resolver=lambda workorder: workorder.total_costs_products_value,
    )
    detail_fretes = _build_workorder_cost_component_details(
        workorders=delivered_workorders,
        include_workshop_ref=include_workshop_ref,
        budget_plan=cost_budget_plan,
        component_label="Fretes",
        amount_resolver=lambda workorder: workorder.total_products_shipping,
    )
    detail_servicos_terceiros = _build_workorder_cost_component_details(
        workorders=delivered_workorders,
        include_workshop_ref=include_workshop_ref,
        budget_plan=cost_budget_plan,
        component_label="Serviços Terceiros",
        amount_resolver=lambda workorder: workorder.total_third_party_services_cost,
    )
    detail_mao_de_obra = _build_workorder_cost_component_details(
        workorders=delivered_workorders,
        include_workshop_ref=include_workshop_ref,
        budget_plan=cost_budget_plan,
        component_label="Custo Mão de Obra da Oficina",
        amount_resolver=lambda workorder: workorder.total_costs_services_value - workorder.total_third_party_services_cost,
    )

    total_custos_de_mercadorias_vendidas = _sum_detail_amounts(detail_taxas_maquininha) + _sum_detail_amounts(detail_custos_pecas) + _sum_detail_amounts(detail_fretes)
    total_custos_de_servicos_vendidos = _sum_detail_amounts(detail_servicos_terceiros) + _sum_detail_amounts(detail_mao_de_obra)
    total_custos = total_custos_de_mercadorias_vendidas + total_custos_de_servicos_vendidos

    detail_custos_mercadorias_vendidas = _build_static_group_tree(
        sections=[
            ("Taxas Maquininhas", detail_taxas_maquininha),
            ("Custos de Peças", detail_custos_pecas),
            ("Fretes", detail_fretes),
        ]
    )
    detail_custos_servicos_vendidos = _build_static_group_tree(
        sections=[
            ("Serviços Terceiros", detail_servicos_terceiros),
            ("Custo Mão de Obra da Oficina", detail_mao_de_obra),
        ]
    )
    # ------

    # Receita Bruta de Vendas
    total_receita_bruta_de_vendas = total_receita_bruta_de_vendas_e_servicos - total_custos
    # -----------------------

    # Receitas Financeiras
    fin_revenue_groups, total_receitas_financeiras = _build_financial_revenue_group_tree(
        payments=pagamentos_ordens_de_servico,
        movements=movements,
        workorder_revenue_movements=workorder_revenue_movements,
        financial_groups=financial_groups,
    )
    detail_receitas_financeiras = fin_revenue_groups
    logger.info(
        "DRE revenue grouped output | %s",
        json.dumps(
            {
                "workshop_ids": [workshop.pk for workshop in workshops],
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "tipo_data": tipo_data,
                "financial_revenue_total": str(total_receitas_financeiras),
                "financial_revenue_groups": _serialize_group_nodes_for_log(fin_revenue_groups),
            },
            ensure_ascii=True,
            default=str,
        ),
    )
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
            label="Custos de Mercadorias Vendidas",
            amount=total_custos_de_mercadorias_vendidas,
            tone="negative",
            component=COMP_COGS,
            detail_kind="group_entries",
            is_expandable=True,
            details=detail_custos_mercadorias_vendidas,
        ),
        _row(
            label="Custos de Serviços Vendidos",
            amount=total_custos_de_servicos_vendidos,
            tone="negative",
            component=COMP_COS,
            detail_kind="group_entries",
            is_expandable=True,
            details=detail_custos_servicos_vendidos,
        ),
        _row(
            label="(=) Receita Líquida",
            amount=total_receita_bruta_de_vendas,
            tone="highlight",
            component=COMP_GROSS_PROFIT,
            formula="Receita Bruta de Vendas e Serviços - Custos de Mercadorias Vendidas - Custos de Serviços Vendidos",
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


def _sum_cost_movements(movements: list[FinancialMovement]) -> Money:
    """Soma custos por valor absoluto para exibição no CMV."""
    total = _ZERO
    for movement in movements:
        amount = movement.amount
        if not isinstance(amount, Money):
            continue
        total += abs(amount)
    return total


def _sum_detail_amounts(details: list[dict]) -> Money:
    total = _ZERO
    for detail in details:
        amount = detail.get("amount", _ZERO)
        if isinstance(amount, Money):
            total += amount
    return total


def _build_workorder_payment_totals(*, payments: list[WorkOrderPaymentMethod]) -> dict[int, Money]:
    totals: dict[int, Money] = {}
    for payment in payments:
        workorder_id = getattr(payment, "workorder_id", None)
        if workorder_id is None:
            continue
        totals[workorder_id] = totals.get(workorder_id, _ZERO) + payment.total_paid
    return totals


def _fetch_delivered_workorders_with_costs(*, payments: list[WorkOrderPaymentMethod]) -> list[tuple[WorkOrder, Money]]:
    workorder_ids = sorted({payment.workorder_id for payment in payments if payment.workorder_id})
    if not workorder_ids:
        return []

    workorders = list(
        WorkOrder.objects.filter(pk__in=workorder_ids)
        .select_related("budget", "budget__customer", "workshop")
        .prefetch_related(
            "payments",
            "items__product",
            "items__service",
            "items__kit",
            "items__kit_overrides",
            "items__kit__kit_products__product",
            "items__kit__kit_services__service",
        )
    )

    payloads: list[tuple[WorkOrder, Money]] = []
    for workorder in workorders:
        if workorder.status != WorkOrderStatus.APPROVED or workorder.delivered_at is None:
            continue

        total_cost = workorder.total_costs_products_value + workorder.total_costs_services_value
        setattr(workorder, "dre_total_cost", total_cost)
        payloads.append((workorder, total_cost))

    return payloads


def _build_financial_revenue_group_tree(
    *,
    payments: list[WorkOrderPaymentMethod],
    movements: list[FinancialMovement],
    workorder_revenue_movements: list[FinancialMovement],
    financial_groups: list[FinancialGroup],
) -> tuple[list[dict], Money]:
    movement_by_workorder_id = {workorder_id: movement for movement in workorder_revenue_movements if (workorder_id := getattr(movement, "workorder_id", None)) is not None}

    revenue_details: list[dict] = []

    for payment in payments:
        workorder_id = getattr(payment, "workorder_id", None)
        if workorder_id is None:
            continue
        movement = movement_by_workorder_id.get(workorder_id)
        if movement is None:
            continue
        group = _resolve_financial_group_for_revenue_movement(movement=movement, financial_groups=financial_groups)
        if group is None or not getattr(group, "pk", None):
            continue
        detail = _build_wo_pm_detail(payment, include_workshop_ref=False)
        detail["budget_plan"] = group
        revenue_details.append(detail)

    for movement in movements:
        if movement.direction != FinancialMovement.MovementDirection.CREDIT:
            continue
        if getattr(movement, "workorder_id", None) is not None:
            continue
        group = getattr(movement, "budget_plan", None)
        if group is None or not getattr(group, "pk", None):
            continue
        detail = _build_detail(movement, include_workshop_ref=False)
        detail["budget_plan"] = group
        revenue_details.append(detail)

    return _build_group_tree_from_details(details=revenue_details, financial_groups=financial_groups)


def _fetch_workorder_revenue_movements(
    *,
    workshops: Sequence[Workshop],
    workorder_ids: list[int],
    selected_financial_groups: list[FinancialGroup] | None = None,
) -> list[FinancialMovement]:
    if not workorder_ids:
        return []

    qs = FinancialMovement.objects.filter(
        workshop__in=workshops,
        workorder_id__in=workorder_ids,
        direction=FinancialMovement.MovementDirection.CREDIT,
        workorder_payment__isnull=True,
    ).exclude(reversal_of__isnull=False)

    if selected_financial_groups:
        qs = qs.filter(Q(budget_plan_id__in=[group.pk for group in selected_financial_groups]) | Q(budget_plan__isnull=True))

    candidate_movements = list(
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
        .order_by("workorder_id", "pk")
    )

    movements_by_workorder: dict[int, FinancialMovement] = {}
    for movement in candidate_movements:
        workorder_id = getattr(movement, "workorder_id", None)
        if workorder_id is None:
            continue

        current = movements_by_workorder.get(workorder_id)
        if current is None:
            movements_by_workorder[workorder_id] = movement
            continue

        current_is_parent = current.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT
        movement_is_parent = movement.movement_kind == FinancialMovement.MovementKind.WORKORDER_PARENT
        if movement_is_parent and not current_is_parent:
            movements_by_workorder[workorder_id] = movement

    return list(movements_by_workorder.values())


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


def _build_detail(m: FinancialMovement, include_workshop_ref: bool, workorder_payment_totals: dict[int, Money] | None = None) -> dict:
    """Monta o dicionário de detalhe de uma movimentação para o template."""
    workorder = getattr(m, "workorder", None)
    budget = getattr(workorder, "budget", None)

    is_workorder_revenue_detail = m.workorder_id and workorder_payment_totals is not None

    if is_workorder_revenue_detail:
        amount = _resolve_workorder_revenue_amount(movement=m, workorder_payment_totals=workorder_payment_totals)
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

    if is_workorder_revenue_detail:
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


def _build_maquininha_detail(m: FinancialMovement, include_workshop_ref: bool, budget_plan: FinancialGroup | None = None) -> dict:
    detail = _build_detail(m, include_workshop_ref)
    detail["budget_plan"] = budget_plan
    return detail


def _build_workorder_cost_detail(wo: WorkOrder, include_workshop_ref: bool, budget_plan: FinancialGroup | None = None) -> dict:
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
        "amount": getattr(wo, "dre_total_cost", wo.total_costs_products_value + wo.total_costs_services_value),
        "budget_plan": budget_plan,
    }


def _build_workorder_cost_component_detail(
    *,
    workorder: WorkOrder,
    include_workshop_ref: bool,
    budget_plan: FinancialGroup | None,
    component_label: str,
    amount: Money,
) -> dict:
    budget = getattr(workorder, "budget", None)
    customer = getattr(budget, "customer", None)
    pk = getattr(budget, "pk", "-")
    name = getattr(customer, "name", "-") or "-"

    reference = f"O.S #{pk}"
    if include_workshop_ref and workorder.workshop_id:
        reference = f"Filial: {workorder.workshop.name} | {reference}"

    return {
        "movement": None,
        "workorder_id": workorder.pk,
        "summary": f"{component_label} - O.S #{pk} - {name}",
        "reference": reference,
        "entry_date": getattr(workorder, "criado_em", None),
        "payment_date": getattr(workorder, "criado_em", None),
        "amount": amount,
        "budget_plan": budget_plan,
    }


def _build_workorder_cost_component_details(
    *,
    workorders: list[WorkOrder],
    include_workshop_ref: bool,
    budget_plan: FinancialGroup | None,
    component_label: str,
    amount_resolver,
) -> list[dict]:
    details: list[dict] = []
    for workorder in workorders:
        amount = amount_resolver(workorder)
        if amount.amount <= Decimal("0.00"):
            continue
        details.append(
            _build_workorder_cost_component_detail(
                workorder=workorder,
                include_workshop_ref=include_workshop_ref,
                budget_plan=budget_plan,
                component_label=component_label,
                amount=amount,
            )
        )
    return details


def _build_static_group_tree(*, sections: list[tuple[str, list[dict]]]) -> list[dict]:
    nodes: list[dict] = []
    for index, (group_name, details) in enumerate(sections, start=1):
        amount = _sum_detail_amounts(details)
        if amount.amount <= Decimal("0.00"):
            continue
        nodes.append(
            {
                "group": _StaticDreGroup(pk=-index, name=group_name),
                "direct_amount": amount,
                "amount": amount,
                "details": details,
                "children": [],
            }
        )
    return nodes


def _resolve_workorder_revenue_amount(*, movement: FinancialMovement, workorder_payment_totals: dict[int, Money] | None = None) -> Money:
    workorder_id = getattr(movement, "workorder_id", None)
    if workorder_id is not None and workorder_payment_totals is not None:
        return workorder_payment_totals.get(workorder_id, _ZERO)

    workorder = getattr(movement, "workorder", None)
    if workorder is None:
        return _ZERO

    payments = list(workorder.payments.all()) if hasattr(workorder, "payments") else []
    return sum((payment.total_paid for payment in payments), _ZERO)


def _should_include_workorder_revenue_movement(*, movement: FinancialMovement, workorder_payment_totals: dict[int, Money] | None = None) -> bool:
    workorder = getattr(movement, "workorder", None)
    if workorder is None:
        return False

    return _resolve_workorder_revenue_amount(movement=movement, workorder_payment_totals=workorder_payment_totals).amount > Decimal("0.00")


def _resolve_financial_group_for_revenue_movement(*, movement: FinancialMovement, financial_groups: list[FinancialGroup]) -> FinancialGroup | None:
    budget_plan = getattr(movement, "budget_plan", None)
    if budget_plan is not None and getattr(budget_plan, "pk", None):
        return budget_plan

    preferred_names = {"vendas", "receitas"}
    root_candidates = [group for group in financial_groups if getattr(group, "parent_id", None) is None and str(getattr(group, "name", "")).strip().lower() in preferred_names]
    if root_candidates:
        root_candidates.sort(key=lambda group: (getattr(group, "sort_key", ""), getattr(group, "pk", 0)))
        return root_candidates[0]

    return None


def _resolve_default_sales_group(*, financial_groups: list[FinancialGroup]) -> FinancialGroup | None:
    preferred_names = {"vendas", "receitas"}
    root_candidates = [group for group in financial_groups if getattr(group, "parent_id", None) is None and str(getattr(group, "name", "")).strip().lower() in preferred_names]
    if root_candidates:
        root_candidates.sort(key=lambda group: (getattr(group, "sort_key", ""), getattr(group, "pk", 0)))
        return root_candidates[0]

    return None


def _build_financial_group_rollup(*, movements: list[FinancialMovement], direction: str, financial_groups: list[FinancialGroup], include_workorder_movements: bool = False, workorder_payment_totals: dict[int, Money] | None = None) -> list[dict]:
    grouped: dict[int, dict] = {}
    groups_by_id = {group.pk: group for group in financial_groups}
    relevant_group_ids: set[int] = set()

    for movement in movements:
        if movement.direction != direction:
            continue
        if workorder_payment_totals is not None and movement.workorder_id is None:
            continue
        if movement.workorder_id is not None and not include_workorder_movements:
            continue
        if movement.workorder_id is not None and not _should_include_workorder_revenue_movement(movement=movement, workorder_payment_totals=workorder_payment_totals):
            continue
        group = _resolve_financial_group_for_revenue_movement(movement=movement, financial_groups=financial_groups) if workorder_payment_totals is not None else getattr(movement, "budget_plan", None)
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
        if movement.direction != direction:
            continue
        if workorder_payment_totals is not None and movement.workorder_id is None:
            continue
        if movement.workorder_id is not None and not include_workorder_movements:
            continue
        if movement.workorder_id is not None and not _should_include_workorder_revenue_movement(movement=movement, workorder_payment_totals=workorder_payment_totals):
            continue

        detail = _build_detail(movement, include_workshop_ref=False, workorder_payment_totals=workorder_payment_totals)
        group = detail.get("budget_plan") or (_resolve_financial_group_for_revenue_movement(movement=movement, financial_groups=financial_groups) if workorder_payment_totals is not None else getattr(movement, "budget_plan", None))
        if group is None or not getattr(group, "pk", None):
            continue
        detail["budget_plan"] = group

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


def _build_financial_group_tree(
    *,
    movements: list[FinancialMovement],
    direction: str,
    financial_groups: list[FinancialGroup],
    include_workorder_movements: bool = False,
    workorder_payment_totals: dict[int, Money] | None = None,
    workorder_revenue_movements: list[FinancialMovement] | None = None,
) -> tuple[list[dict], Money]:
    grouped = _build_financial_group_rollup(
        movements=workorder_revenue_movements if direction == FinancialMovement.MovementDirection.CREDIT and workorder_revenue_movements is not None else movements,
        direction=direction,
        financial_groups=financial_groups,
        include_workorder_movements=include_workorder_movements,
        workorder_payment_totals=workorder_payment_totals,
    )
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


def _build_group_tree_from_details(*, details: list[dict], financial_groups: list[FinancialGroup]) -> tuple[list[dict], Money]:
    grouped: dict[int, dict] = {}
    groups_by_id = {group.pk: group for group in financial_groups}

    for detail in details:
        group = detail.get("budget_plan")
        group_id = getattr(group, "pk", None)
        while group_id:
            if group_id not in grouped and group_id in groups_by_id:
                grouped[group_id] = {
                    "group": groups_by_id[group_id],
                    "amount": _ZERO,
                    "details": [],
                }
            group_id = getattr(groups_by_id.get(group_id), "parent_id", None)

        group = detail.get("budget_plan")
        group_id = getattr(group, "pk", None)
        if group_id is None:
            continue
        grouped.setdefault(
            group_id,
            {
                "group": group,
                "amount": _ZERO,
                "details": [],
            },
        )["details"].append(detail)

    ordered_groups = []
    for payload in grouped.values():
        payload["amount"] = _sum_detail_amounts(payload["details"])
        ordered_groups.append(payload)

    ordered_groups.sort(key=lambda item: (getattr(item["group"], "sort_key", ""), getattr(item["group"], "pk", 0)))
    nodes = _build_group_tree(groups=ordered_groups)
    roots = _build_group_tree_roots(nodes=nodes)
    total = sum((root["amount"] for root in roots), _ZERO)
    return roots, total


def _serialize_group_nodes_for_log(nodes: list[dict]) -> list[dict[str, object]]:
    serialized: list[dict[str, object]] = []
    for node in nodes:
        serialized.append(
            {
                "group_id": getattr(node.get("group"), "pk", None),
                "group_name": getattr(node.get("group"), "name", None),
                "amount": str(node.get("amount", _ZERO)),
                "details": [
                    {
                        "workorder_id": detail.get("workorder_id"),
                        "summary": detail.get("summary"),
                        "amount": str(detail.get("amount", _ZERO)),
                        "budget_plan_id": getattr(detail.get("budget_plan"), "pk", None),
                        "budget_plan_name": getattr(detail.get("budget_plan"), "name", None),
                    }
                    for detail in node.get("details", [])
                ],
                "children": _serialize_group_nodes_for_log(node.get("children", [])),
            }
        )
    return serialized


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
            _row(label="Custos de Mercadorias Vendidas", amount=_ZERO, tone="negative", component=COMP_COGS, detail_kind="group_entries", is_expandable=True),
            _row(label="Custos de Serviços Vendidos", amount=_ZERO, tone="negative", component=COMP_COS, detail_kind="group_entries", is_expandable=True),
            _row(
                label="(=) Receita Líquida",
                amount=_ZERO,
                tone="highlight",
                component=COMP_GROSS_PROFIT,
                formula="Receita Bruta de Vendas e Serviços - Custos de Mercadorias Vendidas - Custos de Serviços Vendidos",
            ),
            _row(label="Receitas Financeiras", amount=_ZERO, tone="positive", component=COMP_FINANCIAL_REVENUE, detail_kind="group_entries", is_expandable=True),
            _row(label="Despesas Financeiras", amount=_ZERO, tone="negative", component=COMP_FINANCIAL_EXPENSE, detail_kind="group_entries", is_expandable=True),
            _row(label="(=) Resultado Operacional", amount=_ZERO, tone="result", component=COMP_OPERATING_RESULT, formula="Receitas Financeiras - Despesas Financeiras"),
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
