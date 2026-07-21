from __future__ import annotations

import logging
import time
from calendar import monthrange
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, TypeVar

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget, BudgetStatus, BudgetType
from apps.budget.service_costs import calculate_mechanic_service_cost
from apps.core.domain.services.dashboard_service import DashboardMetrics
from apps.core.infrastructure.kit_prefetch import budget_items_with_kit_prefetch, budget_kit_overrides_prefetch, workorder_items_with_kit_prefetch, workorder_kit_overrides_prefetch
from apps.core.observability import build_business_metric_attributes, record_business_operation
from apps.finance.services.dre import COMP_COGS, COMP_COS, COMP_GROSS_REVENUE, build_dre_calculation
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import get_mechanic_salary_monthly_cost

logger = logging.getLogger(__name__)
_T = TypeVar("_T")

# ─── Module-level constants ───────────────────────────────────────────────────

MISSING_WORKSHOP_COST_WARNING = "Para realizar o calculo, cadastre um custo mensal da oficina para o mes selecionado."
TWO_DECIMAL_PLACES = Decimal("0.01")

MONTH_LABELS_PT: list[str] = [
    "",
    "Janeiro",
    "Fevereiro",
    "Marco",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]

# Re-export shared kit Prefetch helpers (select_related product/service on overrides).
_BUDGET_KIT_OVERRIDES_PREFETCH = budget_kit_overrides_prefetch()
_WORKORDER_KIT_OVERRIDES_PREFETCH = workorder_kit_overrides_prefetch()

OPEN_BUDGET_STATUSES: tuple[str, ...] = (
    BudgetStatus.DRAFT,
    BudgetStatus.WAITING_CLIENT,
    BudgetStatus.WAITING_DIAGNOSIS,
    BudgetStatus.WAITING_ITEMS,
    BudgetStatus.WAITING_PRICING,
    BudgetStatus.WAITING_REVIEW,
    BudgetStatus.WAITING_APPROVAL,
)

REJECTED_BUDGET_STATUS_VALUES: tuple[str, ...] = (
    BudgetStatus.REJECTED,
    "reprovado",
    "reproved",
)

INDICATOR_LABELS: dict[str, tuple[str, str]] = {
    "a_receber_em_execucao": ("Total A Receber (Em Execução)", "Ordens de Serviço"),
    "a_receber_mes_atual": ("Mês Atual (A Receber)", "Ordens de Serviço"),
    "a_receber_meses_anteriores": ("Meses Anteriores (A Receber)", "Ordens de Serviço"),
    "aguardando_aprovacao": ("Total Aguardando Aprovação", "Orçamentos"),
    "aguardando_aprovacao_mes_atual": ("Mês Atual (Aguardando Aprovação)", "Orçamentos"),
    "aguardando_aprovacao_meses_anteriores": ("Meses Anteriores (Aguardando Aprovação)", "Orçamentos"),
    "reprovados": ("Total Reprovados", "Orçamentos"),
    "carros_mes": ("Carros no Mês", "Ordens de Serviço"),
    "garantia_cortesia_mes": ("Garantia + Cortesia", "Ordens de Serviço"),
}

# ─── Prefetch descriptors (reused across all queries) ─────────────────────────
# Each Prefetch pre-loads item relations so Budget/WorkOrder._iter_items()
# finds results in _prefetched_objects_cache["items"] and avoids N+1 queries.

_BUDGET_ITEMS_PREFETCH = budget_items_with_kit_prefetch()
_WORKORDER_ITEMS_PREFETCH = workorder_items_with_kit_prefetch()


# ─── Value objects (result types for each query) ──────────────────────────────


@dataclass(frozen=True)
class ApprovedBudgetMetrics:
    accumulated_profitability: float | Decimal
    accumulated_markup: Decimal
    approved_count: int


@dataclass(frozen=True)
class ApprovalRateMetrics:
    created_count: int
    approved_count: int


@dataclass(frozen=True)
class PendingReceivableMetrics:
    total_general: Decimal
    monthly: Decimal
    previous_months: Decimal


@dataclass(frozen=True)
class PendingBudgetMetrics:
    total_general: Decimal
    monthly: Decimal
    previous_months: Decimal


@dataclass(frozen=True)
class FinancialIndicatorWorkOrderGroup:
    primary_item: WorkOrder
    child_items: list[WorkOrder]
    primary_amount: Decimal
    group_total: Decimal

    @property
    def child_total(self) -> Decimal:
        return self.group_total - self.primary_amount

    @property
    def has_children(self) -> bool:
        return bool(self.child_items)

    @property
    def is_primary_child(self) -> bool:
        return self.primary_item.budget.reference_budget_id is not None


@dataclass(frozen=True)
class FinancialIndicatorReportData:
    indicator: str
    report_title: str
    periodo_label: str
    items_label: str
    is_budget_report: bool
    total_value: Decimal
    summary_count: int
    record_count: int
    value_column_label: str
    rows: list[Any]
    workorder_groups: list[FinancialIndicatorWorkOrderGroup]


# ─── Pure utility functions ───────────────────────────────────────────────────


def resolve_decimal_amount(value: Any) -> Decimal:
    amount = getattr(value, "amount", value)
    if isinstance(amount, Decimal):
        return amount
    return Decimal(str(amount or "0.00"))


def _format_brl(amount: Decimal) -> str:
    return f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def calculate_aggregate_markup(*, workshop_id: int, month: int, year: int, total_revenue: Decimal | None = None) -> Decimal:
    """Calculate aggregate markup from DRE totals for the selected month.

    Formula: Receita Bruta de Vendas e Serviços / (CMV + CSV)
    where CMV = Custos de Mercadorias Vendidas and CSV = Custos de Serviços Vendidos.

    ``total_revenue`` is accepted for call-site compatibility but ignored; both
    numerator and denominator always come from ``build_dre_calculation``.
    """
    _ = total_revenue

    workshop = Workshop.objects.filter(pk=workshop_id).first()
    if workshop is None:
        return Decimal("0.00")

    start_date = date(year, month, 1)
    end_date = date(year, month, monthrange(year, month)[1])
    dre = build_dre_calculation(workshops=[workshop], start_date=start_date, end_date=end_date)

    amounts_by_component: dict[str, Decimal] = {}
    for row in dre.rows:
        component = row.get("component")
        if not component:
            continue
        amounts_by_component[str(component)] = resolve_decimal_amount(row.get("amount"))

    total_revenue_dre = amounts_by_component.get(COMP_GROSS_REVENUE, Decimal("0.00"))
    total_cogs = amounts_by_component.get(COMP_COGS, Decimal("0.00"))
    total_cos = amounts_by_component.get(COMP_COS, Decimal("0.00"))
    total_cost = total_cogs + total_cos

    if total_revenue_dre == Decimal("0.00") or total_cost <= Decimal("0.00"):
        return Decimal("0.00")

    return (total_revenue_dre / total_cost).quantize(TWO_DECIMAL_PLACES)


def _aggregate_revenue(*, workshop_id: int, month: int, year: int) -> Decimal:
    result = (
        WorkOrderPaymentMethod.objects.filter(
            workorder__workshop_id=workshop_id,
            workorder__status__in=(WorkOrderStatus.APPROVED, WorkOrderStatus.DRAFT),
            workorder__budget_type="sale",
            due_date__month=month,
            due_date__year=year,
        )
        .annotate(
            payment_total=ExpressionWrapper(
                F("first_installment_amount") + (F("installments_count") - 1) * F("remaining_installments_amount"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )
        .aggregate(total=Sum("payment_total"))
    )
    return result["total"] or Decimal("0.00")


def _get_workorder_ids_from_payments(*, workshop_id: int, month: int, year: int) -> list[int]:
    return list(
        WorkOrderPaymentMethod.objects.filter(
            workorder__workshop_id=workshop_id,
            workorder__status__in=(WorkOrderStatus.APPROVED, WorkOrderStatus.DRAFT),
            workorder__budget_type="sale",
            due_date__month=month,
            due_date__year=year,
        )
        .values_list("workorder_id", flat=True)
        .distinct()
    )


def _mark_budget_read_only(budget: Budget | None) -> None:
    if budget is not None:
        setattr(budget, "_read_only_pricing_context", True)


def _build_injected_pricing_context(*, workshop: Workshop, workshop_cost: WorkshopCost | None) -> SimpleNamespace:
    productive_salary_total = Money(0, "BRL")
    working_hours_per_month = Decimal("0.00")
    hourly_cost_value = Money(0, "BRL")
    profitability_multiplier = Decimal("1.00")
    minimum_hourly_cost = Money(0, "BRL")
    month = None
    year = None

    if workshop_cost is not None:
        month = workshop_cost.month
        year = workshop_cost.year
        working_hours_per_month = workshop_cost.working_hours_per_month or Decimal("0.00")
        hourly_cost_value = workshop_cost.hourly_cost_value or Money(0, "BRL")
        profitability_multiplier = workshop_cost.profitability_multiplier or Decimal("1.00")
        minimum_hourly_cost = workshop_cost.minimum_hourly_cost or Money(0, "BRL")
        mechanic_salary_obj = get_mechanic_salary_monthly_cost(workshop=workshop)
        if mechanic_salary_obj is not None:
            salary_item = WorkshopCostItem.objects.filter(workshop_cost=workshop_cost, monthly_cost=mechanic_salary_obj).first()
            if salary_item is not None:
                productive_salary_total = salary_item.amount

    return SimpleNamespace(
        minimum_hourly_cost=minimum_hourly_cost,
        hourly_cost_value=hourly_cost_value,
        profitability_multiplier=profitability_multiplier,
        working_hours_per_month=working_hours_per_month,
        productive_salary_total=productive_salary_total,
        month=month,
        year=year,
    )


def _prepare_budget_for_dashboard_pricing(
    budget: Budget | None,
    *,
    pricing_context: SimpleNamespace | None = None,
    for_totals_only: bool = False,
) -> None:
    if budget is None:
        return
    _mark_budget_read_only(budget)
    if pricing_context is not None:
        setattr(budget, "_injected_pricing_context", pricing_context)
    # Slider 0: labor cost does not change total_budget_value (see build_pricing_snapshot).
    if for_totals_only and int(getattr(budget, "slider", 0) or 0) == 0:
        setattr(budget, "_skip_mechanic_labor_cost", True)


def _prepare_workorder_for_dashboard_pricing(
    workorder: WorkOrder,
    *,
    pricing_context: SimpleNamespace | None = None,
    for_totals_only: bool = False,
) -> None:
    _prepare_budget_for_dashboard_pricing(
        workorder.budget,
        pricing_context=pricing_context,
        for_totals_only=for_totals_only,
    )
    if for_totals_only and workorder.budget is not None and int(getattr(workorder.budget, "slider", 0) or 0) == 0:
        setattr(workorder, "_skip_mechanic_labor_cost", True)


def _mechanic_cost_from_snapshot(*, workorder: WorkOrder, snapshot) -> Decimal:
    budget = workorder.budget
    if budget is None:
        return Decimal("0.00")
    _mark_budget_read_only(budget)
    total = Decimal("0.00")
    for line in snapshot.service_lines:
        if line.third_party:
            continue
        fallback_cost = line.original_cost_total if line.original_cost_total.amount > 0 else line.cost_total
        mechanic_cost = calculate_mechanic_service_cost(
            budget=budget,
            duration=line.duration,
            quantity=1,
            fallback_cost=fallback_cost,
        )
        total += resolve_decimal_amount(mechanic_cost)
    return total


def _aggregate_costs(*, workorder_ids: list[int]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    workorders = list(
        WorkOrder.objects.filter(
            pk__in=workorder_ids,
            delivered_at__isnull=False,
        )
        .select_related("budget__workshop")
        .prefetch_related(_WORKORDER_ITEMS_PREFETCH)
    )
    total_pcost = Decimal("0.00")
    total_third_party = Decimal("0.00")
    total_mechanic = Decimal("0.00")
    total_shipping = Decimal("0.00")
    for workorder in workorders:
        _prepare_workorder_for_dashboard_pricing(workorder, for_totals_only=False)
        snapshot = workorder.pricing_snapshot
        total_pcost += resolve_decimal_amount(snapshot.total_costs_products_value)
        total_third_party += resolve_decimal_amount(snapshot.total_third_party_services_cost)
        total_shipping += resolve_decimal_amount(snapshot.total_products_shipping)
        total_mechanic += _mechanic_cost_from_snapshot(workorder=workorder, snapshot=snapshot)
    logger.debug(
        "aggregate_costs total_pcost=%s total_third_party=%s total_mechanic=%s total_shipping=%s",
        total_pcost,
        total_third_party,
        total_mechanic,
        total_shipping,
    )
    return total_pcost, total_third_party, total_mechanic, total_shipping


def calculate_markup_progress(markup: Decimal) -> int:
    return min(int((markup * Decimal("50")).quantize(Decimal("1"))), 100)


def count_elapsed_business_days(*, workshop_cost: WorkshopCost, today: date) -> int:
    return sum(1 for d in workshop_cost.get_work_day_dates() if d <= today)


# ─── Report building functions ────────────────────────────────────────────────


def resolve_indicator_row_amount(*, item: Any, indicator: str, is_budget_report: bool) -> Decimal:
    if is_budget_report:
        stored = getattr(item, "stored_total_amount", None)
        if stored is not None:
            return resolve_decimal_amount(stored)
        if indicator == "reprovados":
            return resolve_decimal_amount(item.display_total_budget_value)
        return resolve_decimal_amount(item.total_budget_value)

    if indicator.startswith("a_receber"):
        stored_total = getattr(item, "stored_total_amount", None)
        stored_paid = getattr(item, "stored_paid_amount", None)
        if stored_total is not None and stored_paid is not None:
            pending = resolve_decimal_amount(stored_total) - resolve_decimal_amount(stored_paid)
            return max(pending, Decimal("0.00"))
        return resolve_decimal_amount(item.pending_payment_value)

    stored_total = getattr(item, "stored_total_amount", None)
    if stored_total is not None:
        return resolve_decimal_amount(stored_total)
    return resolve_decimal_amount(item.total_budget_value)


def _build_workorder_groups(*, items: list[WorkOrder], indicator: str) -> list[FinancialIndicatorWorkOrderGroup]:
    """Group WorkOrders into parent/child structure for the modal report.

    Primary items: OSs where budget.reference_budget_id is None (same criteria as qtd_carros_mes).
    Child items: OSs where budget.reference_budget_id is set, nested under their parent budget.
    Orphan children (parent not in items) are simply omitted.
    """
    primary_items: list[WorkOrder] = []
    child_map: dict[int, list[WorkOrder]] = {}

    for workorder in items:
        ref_id = workorder.budget.reference_budget_id
        if ref_id is None:
            primary_items.append(workorder)
            continue
        child_map.setdefault(ref_id, []).append(workorder)

    groups: list[FinancialIndicatorWorkOrderGroup] = []
    for workorder in primary_items:
        child_items = child_map.get(workorder.budget.pk, [])
        primary_amount = resolve_indicator_row_amount(item=workorder, indicator=indicator, is_budget_report=False)
        children_total = sum(
            (resolve_indicator_row_amount(item=child, indicator=indicator, is_budget_report=False) for child in child_items),
            Decimal("0.00"),
        )
        groups.append(
            FinancialIndicatorWorkOrderGroup(
                primary_item=workorder,
                child_items=child_items,
                primary_amount=primary_amount,
                group_total=primary_amount + children_total,
            )
        )

    return groups


def _resolve_value_column_label(indicator: str) -> str:
    if indicator.startswith("a_receber"):
        return "Valor pendente"
    if indicator in {"carros_mes", "garantia_cortesia_mes"}:
        return "Valor consolidado"
    return "Valor total"


def build_financial_indicator_report_data(*, indicator: str, month: int, year: int, items: list[Any], is_budget_report: bool) -> FinancialIndicatorReportData:
    report_title, _ = INDICATOR_LABELS[indicator]
    periodo_label = f"{MONTH_LABELS_PT[month]} de {year}"
    items_label = "Orçamentos considerados no cálculo" if is_budget_report else "Ordens de Serviço consideradas no cálculo"

    if is_budget_report:
        return _build_budget_report(
            indicator=indicator,
            report_title=report_title,
            periodo_label=periodo_label,
            items_label=items_label,
            items=items,
        )
    return _build_workorder_report(
        indicator=indicator,
        report_title=report_title,
        periodo_label=periodo_label,
        items_label=items_label,
        items=items,
    )


def _build_budget_report(*, indicator: str, report_title: str, periodo_label: str, items_label: str, items: list[Any]) -> FinancialIndicatorReportData:
    total_value = sum(
        (resolve_indicator_row_amount(item=item, indicator=indicator, is_budget_report=True) for item in items),
        Decimal("0.00"),
    )
    value_column_label = "Valor exibido" if indicator == "reprovados" else "Valor total"
    return FinancialIndicatorReportData(
        indicator=indicator,
        report_title=report_title,
        periodo_label=periodo_label,
        items_label=items_label,
        is_budget_report=True,
        total_value=total_value,
        summary_count=len(items),
        record_count=len(items),
        value_column_label=value_column_label,
        rows=items,
        workorder_groups=[],
    )


def _build_workorder_report(*, indicator: str, report_title: str, periodo_label: str, items_label: str, items: list[Any]) -> FinancialIndicatorReportData:
    workorder_groups = _build_workorder_groups(items=items, indicator=indicator)
    total_value = sum((group.group_total for group in workorder_groups), Decimal("0.00"))
    summary_count = len(workorder_groups)

    if indicator == "carros_mes":
        total_value = sum((resolve_decimal_amount(item.total_budget_value) for item in items), Decimal("0.00"))
        summary_count = sum(1 for item in items if item.budget.reference_budget_id is None)

    return FinancialIndicatorReportData(
        indicator=indicator,
        report_title=report_title,
        periodo_label=periodo_label,
        items_label=items_label,
        is_budget_report=False,
        total_value=total_value,
        summary_count=summary_count,
        record_count=len(items),
        value_column_label=_resolve_value_column_label(indicator),
        rows=[],
        workorder_groups=workorder_groups,
    )


# ─── Target comparison helpers ────────────────────────────────────────────────


def _compute_projection_vs_target(projection: Decimal, target_gross: Decimal) -> dict[str, Any]:
    percentage_achieved = (projection / target_gross * Decimal("100")).quantize(Decimal("0.1"))
    if percentage_achieved >= 100:
        return {"percentual": percentage_achieved, "cor": "success", "seta": "arrow_upward"}
    if percentage_achieved >= 90:
        return {"percentual": percentage_achieved, "cor": "warning", "seta": "arrow_upward"}
    return {"percentual": percentage_achieved, "cor": "error", "seta": "arrow_downward"}


def _compute_daily_vs_target(actual_daily: Decimal, daily_target: Decimal) -> dict[str, Any]:
    if actual_daily >= daily_target:
        return {"cor": "success", "seta": "arrow_upward"}
    return {"cor": "error", "seta": "arrow_downward"}


# ─── DashboardQueryService ────────────────────────────────────────────────────


class DashboardQueryService:
    """Orchestrates all data fetching and computation for the dashboard.

    Responsibilities:
    - Delegate each data category to a focused private query method.
    - Combine raw query results into the DashboardMetrics value object.
    - Keep business rule computations (projection, targets) in dedicated methods.
    """

    def compute(self, workshop: Workshop, selected_month: int, selected_year: int) -> DashboardMetrics:
        started_at = time.perf_counter()
        section_timings_ms: dict[str, float] = {}
        hoje = timezone.localdate()
        workshop_id = workshop.pk

        def _run_section(section_name: str, callback: Callable[[], _T]) -> _T:
            section_started_at = time.perf_counter()
            result = callback()
            section_timings_ms[section_name] = round((time.perf_counter() - section_started_at) * 1000, 2)
            return result

        workshop_cost = _run_section(
            "workshop_cost",
            lambda: WorkshopCost.objects.filter(workshop_id=workshop_id, month=selected_month, year=selected_year).first(),
        )
        pricing_context = _build_injected_pricing_context(workshop=workshop, workshop_cost=workshop_cost)

        total_sold = _run_section(
            "total_sold",
            lambda: self._calculate_total_sold(workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year),
        )
        approved_budget_metrics = _run_section(
            "approved_budget_metrics",
            lambda: self._get_approved_budget_metrics(
                workshop_id=workshop_id,
                selected_month=selected_month,
                selected_year=selected_year,
                total_revenue=total_sold,
                pricing_context=pricing_context,
            ),
        )
        sale_workorders, warranty_workorders = _run_section(
            "delivered_workorders",
            lambda: self._get_delivered_workorders(
                workshop_id=workshop_id,
                selected_month=selected_month,
                selected_year=selected_year,
                pricing_context=pricing_context,
            ),
        )
        cars_this_month, warranty_courtesy_cars, warranty_return_rate = _run_section(
            "delivery_counts",
            lambda: self._compute_delivery_counts_sql(
                workshop_id=workshop_id,
                selected_month=selected_month,
                selected_year=selected_year,
            ),
        )
        today_sales = _run_section(
            "today_sales",
            lambda: self._calculate_today_sales(workshop_id=workshop_id, today=hoje),
        )

        logger.info(
            "Dashboard total vendido calculado | workshop_id=%s mes=%s ano=%s total_vendido=%s",
            workshop_id,
            selected_month,
            selected_year,
            str(total_sold),
        )

        approval_rate_metrics = _run_section(
            "approval_rate_metrics",
            lambda: self._get_approval_rate_metrics(
                workshop_id=workshop_id,
                selected_month=selected_month,
                selected_year=selected_year,
                approved_count=approved_budget_metrics.approved_count,
            ),
        )
        pending_receivable_metrics = _run_section(
            "pending_receivable_metrics",
            lambda: self._get_pending_receivable_metrics(
                workshop_id=workshop_id,
                selected_month=selected_month,
                selected_year=selected_year,
                pricing_context=pricing_context,
            ),
        )
        pending_budget_metrics = _run_section(
            "pending_budget_metrics",
            lambda: self._get_pending_budget_metrics(
                workshop_id=workshop_id,
                selected_month=selected_month,
                selected_year=selected_year,
                pricing_context=pricing_context,
            ),
        )
        total_rejected_budgets = _run_section(
            "rejected_budget_total",
            lambda: self._get_rejected_budget_total(
                workshop_id=workshop_id,
                selected_month=selected_month,
                selected_year=selected_year,
                pricing_context=pricing_context,
            ),
        )

        average_ticket = total_sold / cars_this_month if cars_this_month > 0 else Decimal("0.00")
        approval_rate = (
            (approval_rate_metrics.approved_count / approval_rate_metrics.created_count * 100) if approval_rate_metrics.created_count > 0 else 0
        )

        projection_data = _run_section(
            "projection",
            lambda: self._compute_projection(workshop_cost=workshop_cost, total_sold=total_sold, today=hoje),
        )
        target_data = _run_section(
            "target_metrics",
            lambda: self._compute_target_metrics(
                workshop_cost=workshop_cost,
                total_sold=total_sold,
                projection=projection_data["projection"],
                elapsed_days=projection_data["elapsed_days"],
            ),
        )

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        attributes = build_business_metric_attributes(
            operation_name="compute_dashboard",
            operation_group="dashboard",
            result="success",
        )
        record_business_operation(duration_ms=duration_ms, attributes=attributes)
        logger.info(
            "business_operation_completed",
            extra={
                "operation_name": "compute_dashboard",
                "operation_group": "dashboard",
                "duration_ms": duration_ms,
                "result": "success",
                "workshop_id": workshop_id,
                "selected_month": selected_month,
                "selected_year": selected_year,
                "section_timings_ms": section_timings_ms,
            },
        )

        return DashboardMetrics(
            workshop_id=workshop.pk,
            selected_month=selected_month,
            selected_year=selected_year,
            months=self._month_choices(),
            years=list(range(hoje.year - 3, hoje.year + 2)),
            cars_this_month=cars_this_month,
            cars_this_month_list=sale_workorders,
            warranty_courtesy_cars=warranty_courtesy_cars,
            warranty_courtesy_cars_list=warranty_workorders,
            average_ticket=average_ticket,
            projection=projection_data["projection"],
            projection_warning=projection_data["projection_warning"],
            elapsed_days=projection_data["elapsed_days"],
            remaining_days=projection_data["remaining_days"],
            configured_working_days=projection_data["configured_working_days"],
            business_holidays=projection_data["business_holidays"],
            total_sold_to_date=total_sold,
            today_sales=today_sales,
            accumulated_profitability=approved_budget_metrics.accumulated_profitability,
            accumulated_markup=approved_budget_metrics.accumulated_markup,
            accumulated_markup_progress=calculate_markup_progress(approved_budget_metrics.accumulated_markup),
            warranty_return_rate=warranty_return_rate,
            approval_rate=approval_rate,
            total_pending_receivable=pending_receivable_metrics.total_general,
            total_pending_budgets=pending_budget_metrics.total_general,
            monthly_pending_receivable=pending_receivable_metrics.monthly,
            total_general_pending_receivable=pending_receivable_metrics.total_general,
            previous_months_pending_receivable=pending_receivable_metrics.previous_months,
            total_general_pending_budgets=pending_budget_metrics.total_general,
            monthly_pending_budgets=pending_budget_metrics.monthly,
            previous_months_pending_budgets=pending_budget_metrics.previous_months,
            total_rejected_budgets=total_rejected_budgets,
            gross_revenue_target=target_data["gross_revenue_target"],
            daily_revenue_target=target_data["daily_revenue_target"],
            actual_daily_revenue=target_data["actual_daily_revenue"],
            projection_vs_target=target_data["projection_vs_target"],
            actual_daily_revenue_vs_target=target_data["actual_daily_revenue_vs_target"],
        )

    @staticmethod
    def _month_choices() -> list[tuple[int, str]]:
        return [
            (1, "Janeiro"),
            (2, "Fevereiro"),
            (3, "Março"),
            (4, "Abril"),
            (5, "Maio"),
            (6, "Junho"),
            (7, "Julho"),
            (8, "Agosto"),
            (9, "Setembro"),
            (10, "Outubro"),
            (11, "Novembro"),
            (12, "Dezembro"),
        ]

    @staticmethod
    def _compute_delivery_counts(*, sale_workorders: list[WorkOrder], warranty_workorders: list[WorkOrder]) -> tuple[int, int, float]:
        cars_this_month = sum(1 for wo in sale_workorders if wo.budget.reference_budget_id is None)
        warranty_courtesy_cars = sum(1 for wo in warranty_workorders if wo.budget.reference_budget_id is None)
        warranty_count = sum(1 for wo in warranty_workorders if wo.budget_type == "warranty")
        total_cars_with_warranty = cars_this_month + warranty_count
        warranty_return_rate = warranty_count / total_cars_with_warranty * 100 if total_cars_with_warranty > 0 else 0
        return cars_this_month, warranty_courtesy_cars, warranty_return_rate

    @staticmethod
    def _compute_delivery_counts_sql(*, workshop_id: int, selected_month: int, selected_year: int) -> tuple[int, int, float]:
        delivered = WorkOrder.objects.filter(
            workshop_id=workshop_id,
            status=WorkOrderStatus.APPROVED,
            delivered_at__month=selected_month,
            delivered_at__year=selected_year,
        )
        counts = delivered.aggregate(
            cars_this_month=Count("pk", filter=Q(budget_type="sale", budget__reference_budget_id__isnull=True)),
            warranty_courtesy_cars=Count(
                "pk",
                filter=Q(budget_type__in=("warranty", "courtesy"), budget__reference_budget_id__isnull=True),
            ),
            warranty_count=Count("pk", filter=Q(budget_type="warranty")),
        )
        cars_this_month = int(counts["cars_this_month"] or 0)
        warranty_courtesy_cars = int(counts["warranty_courtesy_cars"] or 0)
        warranty_count = int(counts["warranty_count"] or 0)
        total_cars_with_warranty = cars_this_month + warranty_count
        warranty_return_rate = warranty_count / total_cars_with_warranty * 100 if total_cars_with_warranty > 0 else 0
        return cars_this_month, warranty_courtesy_cars, warranty_return_rate

    @staticmethod
    def _compute_projection(*, workshop_cost: WorkshopCost | None, total_sold: Decimal, today: date) -> dict[str, Any]:
        if workshop_cost is None:
            return {
                "projection": None,
                "projection_warning": MISSING_WORKSHOP_COST_WARNING,
                "elapsed_days": 0,
                "remaining_days": 0,
                "configured_working_days": None,
                "business_holidays": 0,
            }

        elapsed_days = count_elapsed_business_days(workshop_cost=workshop_cost, today=today)
        configured_working_days = int(workshop_cost.work_days_per_month)
        remaining_days = max(configured_working_days - elapsed_days, 0)
        business_holidays = workshop_cost.get_work_day_count()

        if elapsed_days > 0:
            daily_average = total_sold / Decimal(elapsed_days)
            projection = (daily_average * Decimal(remaining_days)) + total_sold
        else:
            projection = total_sold

        return {
            "projection": projection,
            "projection_warning": "",
            "elapsed_days": elapsed_days,
            "remaining_days": remaining_days,
            "configured_working_days": configured_working_days,
            "business_holidays": business_holidays,
        }

    @staticmethod
    def _compute_target_metrics(*, workshop_cost: WorkshopCost | None, total_sold: Decimal, projection: Decimal | None, elapsed_days: int) -> dict[str, Any]:
        base: dict[str, Any] = {
            "gross_revenue_target": None,
            "daily_revenue_target": None,
            "actual_daily_revenue": None,
            "projection_vs_target": None,
            "actual_daily_revenue_vs_target": None,
        }

        if workshop_cost is None or workshop_cost.gross_revenue_target is None:
            return base

        target_gross = resolve_decimal_amount(workshop_cost.gross_revenue_target)
        base["gross_revenue_target"] = target_gross

        working_days = int(workshop_cost.work_days_per_month or 0)
        if working_days > 0:
            base["daily_revenue_target"] = (target_gross / Decimal(working_days)).quantize(Decimal("0.01"))

        if elapsed_days > 0:
            base["actual_daily_revenue"] = (total_sold / Decimal(elapsed_days)).quantize(Decimal("0.01"))

        if projection is not None and target_gross > 0:
            base["projection_vs_target"] = _compute_projection_vs_target(projection, target_gross)

        actual_daily = base["actual_daily_revenue"]
        daily_target = base["daily_revenue_target"]
        if actual_daily is not None and daily_target is not None:
            base["actual_daily_revenue_vs_target"] = _compute_daily_vs_target(actual_daily, daily_target)

        return base

    @staticmethod
    def _calculate_total_sold(*, workshop_id: int, selected_month: int, selected_year: int) -> Decimal:
        result = (
            WorkOrderPaymentMethod.objects.filter(
                workorder__workshop_id=workshop_id,
                workorder__status__in=(WorkOrderStatus.APPROVED, WorkOrderStatus.DRAFT),
                workorder__budget_type="sale",
                due_date__month=selected_month,
                due_date__year=selected_year,
            )
            .annotate(
                payment_total=ExpressionWrapper(
                    F("first_installment_amount") + (F("installments_count") - 1) * F("remaining_installments_amount"),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            )
            .aggregate(total=Sum("payment_total"))
        )
        return result["total"] or Decimal("0.00")

    @staticmethod
    def _calculate_today_sales(*, workshop_id: int, today: date) -> Decimal:
        result = (
            WorkOrderPaymentMethod.objects.filter(
                workorder__workshop_id=workshop_id,
                workorder__status__in=(WorkOrderStatus.APPROVED, WorkOrderStatus.DRAFT),
                workorder__budget_type="sale",
                due_date=today,
            )
            .annotate(
                payment_total=ExpressionWrapper(
                    F("first_installment_amount") + (F("installments_count") - 1) * F("remaining_installments_amount"),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            )
            .aggregate(total=Sum("payment_total"))
        )
        return result["total"] or Decimal("0.00")

    @staticmethod
    def _get_delivered_workorders(
        *,
        workshop_id: int,
        selected_month: int,
        selected_year: int,
        pricing_context: SimpleNamespace | None = None,
    ) -> tuple[list[WorkOrder], list[WorkOrder]]:
        del pricing_context  # Display totals use stored denormalized amounts.
        all_workorders = list(
            WorkOrder.objects.filter(
                workshop_id=workshop_id,
                status=WorkOrderStatus.APPROVED,
                delivered_at__month=selected_month,
                delivered_at__year=selected_year,
            )
            .select_related("budget__customer", "budget__vehicle", "budget__reference_budget", "budget__workshop")
            .prefetch_related(_WORKORDER_ITEMS_PREFETCH)
            .order_by("delivered_at", "pk")
        )
        for workorder in all_workorders:
            stored_total = getattr(workorder, "stored_total_amount", None)
            display_total = stored_total if stored_total is not None else Money(0, "BRL")
            setattr(workorder, "dashboard_display_total", display_total)
        sale_workorders = [wo for wo in all_workorders if wo.budget_type == "sale"]
        warranty_workorders = [wo for wo in all_workorders if wo.budget_type in ("warranty", "courtesy")]
        return sale_workorders, warranty_workorders

    @staticmethod
    def _get_approved_budget_metrics(
        *,
        workshop_id: int,
        selected_month: int,
        selected_year: int,
        total_revenue: Decimal | None = None,
        pricing_context: SimpleNamespace | None = None,
    ) -> ApprovedBudgetMetrics:
        approved_budgets = list(
            Budget.objects.filter(
                workshop_id=workshop_id,
                status=BudgetStatus.APPROVED,
                entry_date__month=selected_month,
                entry_date__year=selected_year,
            )
            .select_related("workshop")
            .prefetch_related(_BUDGET_ITEMS_PREFETCH)
        )
        profitabilities: list[Any] = []
        for budget in approved_budgets:
            _prepare_budget_for_dashboard_pricing(budget, pricing_context=pricing_context, for_totals_only=True)
            rentability = budget.rentability
            if rentability is not None:
                profitabilities.append(rentability)
        accumulated_profitability = sum(profitabilities) / len(profitabilities) if profitabilities else 0
        accumulated_markup = calculate_aggregate_markup(
            workshop_id=workshop_id,
            month=selected_month,
            year=selected_year,
            total_revenue=total_revenue,
        )
        return ApprovedBudgetMetrics(
            accumulated_profitability=accumulated_profitability,
            accumulated_markup=accumulated_markup,
            approved_count=len(approved_budgets),
        )

    @staticmethod
    def _get_approval_rate_metrics(*, workshop_id: int, selected_month: int, selected_year: int, approved_count: int | None = None) -> ApprovalRateMetrics:
        created_count = (
            Budget.objects.filter(
                workshop_id=workshop_id,
                entry_date__month=selected_month,
                entry_date__year=selected_year,
            )
            .exclude(budget_type__in=["warranty", "courtesy"])
            .exclude(status=BudgetStatus.CANCELLED)
            .count()
        )
        if approved_count is None:
            approved_count = Budget.objects.filter(
                workshop_id=workshop_id,
                status=BudgetStatus.APPROVED,
                entry_date__month=selected_month,
                entry_date__year=selected_year,
            ).count()
        return ApprovalRateMetrics(created_count=created_count, approved_count=approved_count)

    @staticmethod
    def _get_pending_receivable_metrics(
        *,
        workshop_id: int,
        selected_month: int,
        selected_year: int,
        pricing_context: SimpleNamespace | None = None,
    ) -> PendingReceivableMetrics:
        """Computes total pending receivable for draft OSs, split by current vs previous months."""
        del pricing_context  # Totals come from stored denormalized amounts.
        decimal_out = DecimalField(max_digits=14, decimal_places=2)
        pending_expr = Greatest(
            Coalesce(F("stored_total_amount"), Value(Decimal("0.00"))) - Coalesce(F("stored_paid_amount"), Value(Decimal("0.00"))),
            Value(Decimal("0.00")),
            output_field=decimal_out,
        )
        aggregates = (
            WorkOrder.objects.filter(
                workshop_id=workshop_id,
                status=WorkOrderStatus.DRAFT,
                budget__isnull=False,
            )
            .annotate(pending_amount=pending_expr)
            .aggregate(
                total_general=Coalesce(Sum("pending_amount"), Value(Decimal("0.00")), output_field=decimal_out),
                monthly=Coalesce(
                    Sum("pending_amount", filter=Q(criado_em__month=selected_month, criado_em__year=selected_year)),
                    Value(Decimal("0.00")),
                    output_field=decimal_out,
                ),
            )
        )
        total_general = aggregates["total_general"] or Decimal("0.00")
        monthly = aggregates["monthly"] or Decimal("0.00")
        return PendingReceivableMetrics(
            total_general=total_general,
            monthly=monthly,
            previous_months=total_general - monthly,
        )

    @staticmethod
    def _get_pending_budget_metrics(
        *,
        workshop_id: int,
        selected_month: int,
        selected_year: int,
        pricing_context: SimpleNamespace | None = None,
    ) -> PendingBudgetMetrics:
        del pricing_context  # Totals come from stored denormalized amounts.
        decimal_out = DecimalField(max_digits=14, decimal_places=2)
        aggregates = Budget.objects.filter(
            workshop_id=workshop_id,
            budget_type=BudgetType.SALE,
            status__in=OPEN_BUDGET_STATUSES,
        ).aggregate(
            total_general=Coalesce(Sum("stored_total_amount"), Value(Decimal("0.00")), output_field=decimal_out),
            monthly=Coalesce(
                Sum(
                    "stored_total_amount",
                    filter=Q(entry_date__month=selected_month, entry_date__year=selected_year),
                ),
                Value(Decimal("0.00")),
                output_field=decimal_out,
            ),
        )
        total_general = aggregates["total_general"] or Decimal("0.00")
        monthly = aggregates["monthly"] or Decimal("0.00")
        return PendingBudgetMetrics(
            total_general=total_general,
            monthly=monthly,
            previous_months=total_general - monthly,
        )

    @staticmethod
    def _get_rejected_budget_total(
        *,
        workshop_id: int,
        selected_month: int,
        selected_year: int,
        pricing_context: SimpleNamespace | None = None,
    ) -> Decimal:
        del pricing_context  # Totals come from stored denormalized amounts.
        decimal_out = DecimalField(max_digits=14, decimal_places=2)
        result = Budget.objects.filter(
            workshop_id=workshop_id,
            status__in=REJECTED_BUDGET_STATUS_VALUES,
            entry_date__month=selected_month,
            entry_date__year=selected_year,
        ).aggregate(total=Coalesce(Sum("stored_total_amount"), Value(Decimal("0.00")), output_field=decimal_out))
        return result["total"] or Decimal("0.00")


# ─── Indicator query config ───────────────────────────────────────────────────

_INDICATOR_QUERIES: dict[str, dict[str, Any]] = {
    "a_receber_em_execucao": {
        "model": "workorder",
        "filters": {"status": WorkOrderStatus.DRAFT},
        "date_field": "criado_em",
        "value_field": "pending_payment_value",
        "exclude_month": False,
    },
    "a_receber_mes_atual": {
        "model": "workorder",
        "filters": {"status": WorkOrderStatus.DRAFT},
        "date_field": "criado_em",
        "value_field": "pending_payment_value",
        "exclude_month": False,
    },
    "a_receber_meses_anteriores": {
        "model": "workorder",
        "filters": {"status": WorkOrderStatus.DRAFT},
        "date_field": "criado_em",
        "value_field": "pending_payment_value",
        "exclude_month": True,
    },
    "aguardando_aprovacao": {
        "model": "budget",
        "filters": {"budget_type": BudgetType.SALE, "status__in": OPEN_BUDGET_STATUSES},
        "date_field": "entry_date",
        "value_field": "total_budget_value",
        "exclude_month": False,
    },
    "aguardando_aprovacao_mes_atual": {
        "model": "budget",
        "filters": {"budget_type": BudgetType.SALE, "status__in": OPEN_BUDGET_STATUSES},
        "date_field": "entry_date",
        "value_field": "total_budget_value",
        "exclude_month": False,
    },
    "aguardando_aprovacao_meses_anteriores": {
        "model": "budget",
        "filters": {"budget_type": BudgetType.SALE, "status__in": OPEN_BUDGET_STATUSES},
        "date_field": "entry_date",
        "value_field": "total_budget_value",
        "exclude_month": True,
    },
    "reprovados": {
        "model": "budget",
        "filters": {"status__in": REJECTED_BUDGET_STATUS_VALUES},
        "date_field": "entry_date",
        "value_field": "display_total_budget_value",
        "exclude_month": False,
    },
    "carros_mes": {
        "model": "workorder",
        "filters": {"budget_type": "sale", "status": WorkOrderStatus.APPROVED},
        "date_field": "delivered_at",
        "value_field": "total_budget_value",
        "exclude_month": False,
    },
    "garantia_cortesia_mes": {
        "model": "workorder",
        "filters": {
            "budget_type__in": ["warranty", "courtesy"],
            "status": WorkOrderStatus.APPROVED,
            "budget__reference_budget__isnull": True,
        },
        "date_field": "delivered_at",
        "value_field": None,
        "exclude_month": False,
    },
}


def get_financial_indicator_data(
    workshop: Workshop,
    indicator: str,
    month: int,
    year: int,
) -> tuple[list[Any], bool, str]:
    query_config = _INDICATOR_QUERIES.get(indicator)
    if query_config is None:
        return [], False, "R$ 0,00"

    filters = {**query_config["filters"], "workshop": workshop}
    date_field: str = query_config["date_field"]
    date_filter = {f"{date_field}__month": month, f"{date_field}__year": year}
    model_name: str = query_config["model"]

    if query_config.get("exclude_month"):
        queryset = _build_indicator_queryset(model_name, filters).exclude(**date_filter)
    elif indicator in ("a_receber_em_execucao", "aguardando_aprovacao"):
        queryset = _build_indicator_queryset(model_name, filters)
    else:
        queryset = _build_indicator_queryset(model_name, {**filters, **date_filter})

    items = list(queryset)
    is_budget_report = model_name == "budget"
    value_field = query_config["value_field"]

    if value_field is None:
        total_label = f"{len(items)} veículo(s)"
        return items, is_budget_report, total_label

    total = sum(
        (resolve_indicator_row_amount(item=item, indicator=indicator, is_budget_report=is_budget_report) for item in items),
        Decimal("0.00"),
    )
    return items, is_budget_report, _format_brl(total)


def _build_indicator_queryset(model_name: str, filters: dict[str, Any]):
    """Build an optimized queryset for financial indicator modal/PDF reports.

    Uses prefetch_related to pre-load all item relations, eliminating N+1 queries
    when computing total_budget_value and pending_payment_value per item.
    """
    if model_name == "budget":
        return Budget.objects.filter(**filters).select_related("customer", "vehicle").prefetch_related(_BUDGET_ITEMS_PREFETCH).order_by("entry_date")
    return WorkOrder.objects.filter(**filters).select_related("budget__customer", "budget__vehicle").prefetch_related(_WORKORDER_ITEMS_PREFETCH, "payments").order_by("criado_em")
