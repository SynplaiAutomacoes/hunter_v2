from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from _decimal import Decimal
from django.db.models import DecimalField, ExpressionWrapper, F, Prefetch, Sum
from django.utils import timezone

from apps.budget.models import Budget, BudgetItem, BudgetStatus, BudgetType
from apps.budget.pdf_context import calculate_markup_multiplier
from apps.budget.service_costs import calculate_mechanic_service_cost
from apps.core.domain.services.dashboard_service import DashboardMetrics
from apps.core.observability import build_business_metric_attributes, record_business_operation
from apps.finance.models import FinancialGroup, FinancialMovement
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop

logger = logging.getLogger(__name__)

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

_BUDGET_ITEMS_PREFETCH = Prefetch(
    "items",
    queryset=BudgetItem.objects.select_related("product", "service", "kit").prefetch_related(
        "kit_overrides",
        "kit__kit_products__product",
        "kit__kit_services__service",
    ),
)

_WORKORDER_ITEMS_PREFETCH = Prefetch(
    "items",
    queryset=WorkOrderItem.objects.select_related("product", "service", "kit").prefetch_related(
        "kit_overrides",
        "kit__kit_products__product",
        "kit__kit_services__service",
    ),
)


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


def calculate_aggregate_markup(*, workshop_id: int, month: int, year: int) -> Decimal:
    """Calculate aggregate markup aligned with DRE methodology.

    Formula: SUM(total_paid) / SUM(total_costs_products_value + total_costs_services_value + total_products_shipping)

    Uses WorkOrderPaymentMethod due_date (same as DRE) instead of Budget entry_date.
    """
    total_revenue = _aggregate_revenue(workshop_id=workshop_id, month=month, year=year)
    if total_revenue == Decimal("0.00"):
        return Decimal("0.00")

    workorder_ids = _get_workorder_ids_from_payments(workshop_id=workshop_id, month=month, year=year)
    if not workorder_ids:
        return Decimal("0.00")

    total_product_cost, total_third_party_cost, total_mechanic_cost, total_shipping = _aggregate_costs(workorder_ids=workorder_ids)

    total_service_cost = total_third_party_cost + total_mechanic_cost
    total_cost = total_product_cost + total_service_cost + total_shipping
    if total_cost <= Decimal("0.00"):
        return Decimal("0.00")

    markup = (total_revenue / total_cost).quantize(TWO_DECIMAL_PLACES)

    return markup


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


def _calculate_dre_local_cost(workorder: WorkOrder) -> Decimal:
    budget = workorder.budget
    if budget is None:
        return Decimal("0.00")
    snapshot = budget.pricing_snapshot
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


def _aggregate_costs(*, workorder_ids: list[int]) -> tuple[int, int, int, int]:
    workorders = list(
        WorkOrder.objects.filter(
            pk__in=workorder_ids,
            delivered_at__isnull=False,
        )
        .select_related("budget")
        .prefetch_related(_WORKORDER_ITEMS_PREFETCH)
    )
    total_pcost = sum(resolve_decimal_amount(wo.total_costs_products_value) for wo in workorders)
    total_third_party = sum(resolve_decimal_amount(wo.total_third_party_services_cost) for wo in workorders)
    total_mechanic = sum(_calculate_dre_local_cost(wo) for wo in workorders)
    total_shipping = sum(resolve_decimal_amount(wo.total_products_shipping) for wo in workorders)
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
        if indicator == "reprovados":
            return resolve_decimal_amount(item.display_total_budget_value)
        return resolve_decimal_amount(item.total_budget_value)

    if indicator.startswith("a_receber"):
        return resolve_decimal_amount(item.pending_payment_value)

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
        hoje = timezone.localdate()
        workshop_id = workshop.pk

        workshop_cost = WorkshopCost.objects.filter(workshop_id=workshop_id, month=selected_month, year=selected_year).first()

        approved_budget_metrics = self._get_approved_budget_metrics(workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year)
        sale_workorders, warranty_workorders = self._get_delivered_workorders(workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year)
        total_sold = self._calculate_total_sold(workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year)
        today_sales = self._calculate_today_sales(workshop_id=workshop_id, today=hoje)

        logger.info(
            "Dashboard total vendido calculado | workshop_id=%s mes=%s ano=%s total_vendido=%s",
            workshop_id,
            selected_month,
            selected_year,
            str(total_sold),
        )

        approval_rate_metrics = self._get_approval_rate_metrics(workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year)
        pending_receivable_metrics = self._get_pending_receivable_metrics(workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year)
        pending_budget_metrics = self._get_pending_budget_metrics(workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year)
        total_rejected_budgets = self._get_rejected_budget_total(workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year)

        cars_this_month, warranty_courtesy_cars, warranty_return_rate = self._compute_delivery_counts(sale_workorders=sale_workorders, warranty_workorders=warranty_workorders)
        average_ticket = total_sold / cars_this_month if cars_this_month > 0 else Decimal("0.00")
        approval_rate = (approval_rate_metrics.approved_count / approval_rate_metrics.created_count * 100) if approval_rate_metrics.created_count > 0 else 0

        projection_data = self._compute_projection(workshop_cost=workshop_cost, total_sold=total_sold, today=hoje)
        target_data = self._compute_target_metrics(
            workshop_cost=workshop_cost,
            total_sold=total_sold,
            projection=projection_data["projection"],
            elapsed_days=projection_data["elapsed_days"],
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
    def _get_delivered_workorders(*, workshop_id: int, selected_month: int, selected_year: int) -> tuple[list[WorkOrder], list[WorkOrder]]:
        all_workorders = list(
            WorkOrder.objects.filter(
                workshop_id=workshop_id,
                status=WorkOrderStatus.APPROVED,
                delivered_at__month=selected_month,
                delivered_at__year=selected_year,
            )
            .select_related("budget__customer", "budget__vehicle")
            .prefetch_related(_WORKORDER_ITEMS_PREFETCH)
            .order_by("delivered_at", "pk")
        )
        sale_workorders = [wo for wo in all_workorders if wo.budget_type == "sale"]
        warranty_workorders = [wo for wo in all_workorders if wo.budget_type in ("warranty", "courtesy")]
        return sale_workorders, warranty_workorders

    @staticmethod
    def _get_approved_budget_metrics(*, workshop_id: int, selected_month: int, selected_year: int) -> ApprovedBudgetMetrics:
        approved_budgets = list(
            Budget.objects.filter(
                workshop_id=workshop_id,
                status=BudgetStatus.APPROVED,
                entry_date__month=selected_month,
                entry_date__year=selected_year,
            ).prefetch_related(_BUDGET_ITEMS_PREFETCH)
        )
        profitabilities = [b.rentability for b in approved_budgets if b.rentability is not None]
        accumulated_profitability = sum(profitabilities) / len(profitabilities) if profitabilities else 0
        accumulated_markup = calculate_aggregate_markup(workshop_id=workshop_id, month=selected_month, year=selected_year)
        return ApprovedBudgetMetrics(
            accumulated_profitability=accumulated_profitability,
            accumulated_markup=accumulated_markup,
            approved_count=len(approved_budgets),
        )

    @staticmethod
    def _get_approval_rate_metrics(*, workshop_id: int, selected_month: int, selected_year: int) -> ApprovalRateMetrics:
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
        approved_count = Budget.objects.filter(
            workshop_id=workshop_id,
            status=BudgetStatus.APPROVED,
            entry_date__month=selected_month,
            entry_date__year=selected_year,
        ).count()
        return ApprovalRateMetrics(created_count=created_count, approved_count=approved_count)

    @staticmethod
    def _get_pending_receivable_metrics(*, workshop_id: int, selected_month: int, selected_year: int) -> PendingReceivableMetrics:
        """Computes total pending receivable for all draft OSs, split by current vs previous months.
        Requires items and payments prefetched to calculate pending_payment_value without N+1 queries.
        """
        draft_workorders = list(
            WorkOrder.objects.filter(
                workshop_id=workshop_id,
                status=WorkOrderStatus.DRAFT,
            )
            .select_related("budget")
            .prefetch_related(_WORKORDER_ITEMS_PREFETCH, "payments")
        )

        total_general = Decimal("0.00")
        monthly = Decimal("0.00")
        for workorder in draft_workorders:
            pending_value = resolve_decimal_amount(workorder.pending_payment_value)
            total_general += pending_value
            if workorder.criado_em and workorder.criado_em.month == selected_month and workorder.criado_em.year == selected_year:
                monthly += pending_value

        return PendingReceivableMetrics(
            total_general=total_general,
            monthly=monthly,
            previous_months=total_general - monthly,
        )

    @staticmethod
    def _get_pending_budget_metrics(*, workshop_id: int, selected_month: int, selected_year: int) -> PendingBudgetMetrics:
        pending_budgets = list(
            Budget.objects.filter(
                workshop_id=workshop_id,
                budget_type=BudgetType.SALE,
                status__in=OPEN_BUDGET_STATUSES,
            ).prefetch_related(_BUDGET_ITEMS_PREFETCH)
        )
        total_general = sum((b.total_budget_value.amount for b in pending_budgets), Decimal("0.00"))
        monthly = sum(
            (b.total_budget_value.amount for b in pending_budgets if b.entry_date and b.entry_date.month == selected_month and b.entry_date.year == selected_year),
            Decimal("0.00"),
        )
        return PendingBudgetMetrics(
            total_general=total_general,
            monthly=monthly,
            previous_months=total_general - monthly,
        )

    @staticmethod
    def _get_rejected_budget_total(*, workshop_id: int, selected_month: int, selected_year: int) -> Decimal:
        rejected_budgets = list(
            Budget.objects.filter(
                workshop_id=workshop_id,
                status__in=REJECTED_BUDGET_STATUS_VALUES,
                entry_date__month=selected_month,
                entry_date__year=selected_year,
            ).prefetch_related(_BUDGET_ITEMS_PREFETCH)
        )
        return sum(
            (resolve_decimal_amount(b.display_total_budget_value) for b in rejected_budgets),
            Decimal("0.00"),
        )


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
        (resolve_decimal_amount(getattr(item, value_field)) for item in items),
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
