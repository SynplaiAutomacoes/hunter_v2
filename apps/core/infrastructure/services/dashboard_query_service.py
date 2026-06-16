from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.budget.models import Budget, BudgetStatus, BudgetType
from apps.budget.pdf_context import calculate_markup_multiplier
from apps.core.domain.services.dashboard_service import DashboardMetrics
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop

logger = logging.getLogger(__name__)

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


def resolve_decimal_amount(value: Any) -> Decimal:
    amount = getattr(value, "amount", value)
    if isinstance(amount, Decimal):
        return amount
    return Decimal(str(amount or "0.00"))


def _format_brl(amount: Decimal) -> str:
    return f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def calculate_average_markup(budgets: list[Budget]) -> Decimal:
    markups = [
        calculate_markup_multiplier(
            total_budget_value=budget.total_budget_value,
            total_costs_products_value=budget.total_costs_products_value,
            total_costs_services_value=budget.total_costs_services_value,
        )
        for budget in budgets
    ]
    positive_markups = [markup for markup in markups if markup > 0]
    if not positive_markups:
        return Decimal("0.00")

    return (sum(positive_markups, Decimal("0.00")) / Decimal(len(positive_markups))).quantize(TWO_DECIMAL_PLACES)


def calculate_markup_progress(markup: Decimal) -> int:
    return min(int((markup * Decimal("50")).quantize(Decimal("1"))), 100)


def count_elapsed_business_days(*, workshop_cost: WorkshopCost, today: date) -> int:
    work_day_dates = workshop_cost.get_work_day_dates()
    return sum(1 for d in work_day_dates if d <= today)


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


def resolve_indicator_row_amount(*, item: Any, indicator: str, is_budget_report: bool) -> Decimal:
    if is_budget_report:
        if indicator == "reprovados":
            return resolve_decimal_amount(item.display_total_budget_value)
        return resolve_decimal_amount(item.total_budget_value)

    if indicator.startswith("a_receber"):
        return resolve_decimal_amount(item.pending_payment_value)

    return resolve_decimal_amount(item.total_budget_value)


def _build_workorder_groups(*, items: list[WorkOrder], indicator: str) -> list[FinancialIndicatorWorkOrderGroup]:
    selected_budget_ids = {workorder.budget.pk for workorder in items}
    child_map: dict[int, list[WorkOrder]] = {}
    primary_items: list[WorkOrder] = []

    for workorder in items:
        reference_budget_id = workorder.budget.reference_budget_id
        if reference_budget_id is not None and reference_budget_id in selected_budget_ids:
            child_map.setdefault(reference_budget_id, []).append(workorder)
            continue

        primary_items.append(workorder)

    groups: list[FinancialIndicatorWorkOrderGroup] = []
    for workorder in primary_items:
        child_items = child_map.get(workorder.budget.pk, [])
        primary_amount = resolve_indicator_row_amount(item=workorder, indicator=indicator, is_budget_report=False)
        group_total = primary_amount + sum(
            (resolve_indicator_row_amount(item=child, indicator=indicator, is_budget_report=False) for child in child_items),
            Decimal("0.00"),
        )
        groups.append(
            FinancialIndicatorWorkOrderGroup(
                primary_item=workorder,
                child_items=child_items,
                primary_amount=primary_amount,
                group_total=group_total,
            )
        )

    return groups


def build_financial_indicator_report_data(*, indicator: str, month: int, year: int, items: list[Any], is_budget_report: bool) -> FinancialIndicatorReportData:
    report_title, _ = INDICATOR_LABELS[indicator]
    periodo_label = f"{MONTH_LABELS_PT[month]} de {year}"
    items_label = "Orçamentos considerados no cálculo" if is_budget_report else "Ordens de Serviço consideradas no cálculo"

    if is_budget_report:
        total_value = sum(
            (resolve_indicator_row_amount(item=item, indicator=indicator, is_budget_report=True) for item in items),
            Decimal("0.00"),
        )
        return FinancialIndicatorReportData(
            indicator=indicator,
            report_title=report_title,
            periodo_label=periodo_label,
            items_label=items_label,
            is_budget_report=True,
            total_value=total_value,
            summary_count=len(items),
            record_count=len(items),
            value_column_label="Valor total" if indicator != "reprovados" else "Valor exibido",
            rows=items,
            workorder_groups=[],
        )

    workorder_groups = _build_workorder_groups(items=items, indicator=indicator)
    total_value = sum((group.group_total for group in workorder_groups), Decimal("0.00"))

    value_column_label = "Valor total"
    if indicator.startswith("a_receber"):
        value_column_label = "Valor pendente"
    elif indicator in {"carros_mes", "garantia_cortesia_mes"}:
        value_column_label = "Valor consolidado"

    if indicator == "carros_mes":
        total_value = sum((resolve_decimal_amount(item.total_budget_value) for item in items), Decimal("0.00"))

    return FinancialIndicatorReportData(
        indicator=indicator,
        report_title=report_title,
        periodo_label=periodo_label,
        items_label=items_label,
        is_budget_report=False,
        total_value=total_value,
        summary_count=len(workorder_groups),
        record_count=len(items),
        value_column_label=value_column_label,
        rows=[],
        workorder_groups=workorder_groups,
    )


class DashboardQueryService:
    def compute(
        self,
        workshop: Workshop,
        selected_month: int,
        selected_year: int,
    ) -> DashboardMetrics:
        hoje = timezone.localdate()
        workshop_id = workshop.pk

        workshop_cost = WorkshopCost.objects.filter(workshop_id=workshop_id, month=selected_month, year=selected_year).first()
        approved_budget_metrics = self._get_approved_budget_metrics(workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year)
        sale_workorders, warranty_workorders = self._get_delivered_workorders(workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year)
        total_sold = self._calculate_total_sold(workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year)

        logger.info("Dashboard total vendido calculado | workshop_id=%s mes=%s ano=%s total_vendido=%s",
            workshop_id, selected_month, selected_year, str(total_sold))

        approval_rate_metrics = self._get_approval_rate_metrics(workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year)
        pending_receivable_metrics = self._get_pending_receivable_metrics(workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year)
        pending_budget_metrics = self._get_pending_budget_metrics(workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year)
        total_rejected_budgets = self._get_rejected_budget_total(workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year)

        # === Derived metrics ===
        cars_this_month = sum(1 for wo in sale_workorders if wo.budget.reference_budget_id is None)
        average_ticket = total_sold / cars_this_month if cars_this_month > 0 else Decimal("0.00")
        warranty_courtesy_cars = sum(1 for wo in warranty_workorders if wo.budget.reference_budget_id is None)
        warranty_count = sum(1 for wo in warranty_workorders if wo.budget_type == "warranty")
        total_cars_with_warranty = cars_this_month + warranty_count
        warranty_return_rate = (warranty_count / total_cars_with_warranty * 100) if total_cars_with_warranty > 0 else 0
        approval_rate = (approval_rate_metrics.approved_count / approval_rate_metrics.created_count * 100) if approval_rate_metrics.created_count > 0 else 0

        # === Days, projection, revenue target ===
        elapsed_days = 0
        remaining_days = 0
        projection: Decimal | None = None
        projection_warning = ""
        configured_working_days = int(workshop_cost.work_days_per_month) if workshop_cost is not None else None
        business_holidays = workshop_cost.get_work_day_count() if workshop_cost is not None else 0

        if workshop_cost is not None:
            elapsed_days = count_elapsed_business_days(workshop_cost=workshop_cost, today=hoje)
            remaining_days = max(int(workshop_cost.work_days_per_month or 0) - elapsed_days, 0)
            if elapsed_days > 0:
                daily_average = total_sold / Decimal(elapsed_days)
                projection = (daily_average * Decimal(remaining_days)) + total_sold
            else:
                projection = total_sold
        else:
            projection_warning = MISSING_WORKSHOP_COST_WARNING

        gross_revenue_target = None
        daily_revenue_target = None
        actual_daily_revenue = None
        projection_vs_target = None

        if workshop_cost is not None and workshop_cost.gross_revenue_target is not None:
            target_gross = resolve_decimal_amount(workshop_cost.gross_revenue_target)
            target_gross_val = target_gross if isinstance(target_gross, Decimal) else Decimal(target_gross)
            gross_revenue_target = target_gross_val

            working_days = int(workshop_cost.work_days_per_month or 0)
            if working_days > 0:
                daily_revenue_target = (target_gross_val / Decimal(working_days)).quantize(Decimal("0.01"))

            if elapsed_days > 0:
                actual_daily_revenue = (total_sold / Decimal(elapsed_days)).quantize(Decimal("0.01"))

            if projection is not None and target_gross_val > 0:
                percentage_achieved = (projection / target_gross_val) * Decimal("100")
                percentage_achieved = percentage_achieved.quantize(Decimal("0.1"))

                if percentage_achieved >= 100:
                    color = "success"
                    arrow = "arrow_upward"
                elif percentage_achieved >= 90:
                    color = "warning"
                    arrow = "arrow_upward"
                else:
                    color = "error"
                    arrow = "arrow_downward"

                projection_vs_target = {
                    "percentual": percentage_achieved,
                    "cor": color,
                    "seta": arrow,
                }

            actual_daily_revenue_vs_target = None
            if actual_daily_revenue is not None and daily_revenue_target is not None:
                daily_color = "error"
                daily_arrow = "arrow_downward"

                if actual_daily_revenue >= daily_revenue_target:
                    daily_color = "success"
                    daily_arrow = "arrow_upward"

                actual_daily_revenue_vs_target = {
                    "cor": daily_color,
                    "seta": daily_arrow,
                }

        return DashboardMetrics(
            workshop_id=workshop.pk,
            selected_month=selected_month,
            selected_year=selected_year,
            months=[(1, "Janeiro"), (2, "Fevereiro"), (3, "Março"), (4, "Abril"), (5, "Maio"), (6, "Junho"), (7, "Julho"), (8, "Agosto"), (9, "Setembro"), (10, "Outubro"), (11, "Novembro"), (12, "Dezembro")],
            years=list(range(hoje.year - 3, hoje.year + 2)),
            cars_this_month=cars_this_month,
            cars_this_month_list=sale_workorders,
            warranty_courtesy_cars=warranty_courtesy_cars,
            warranty_courtesy_cars_list=warranty_workorders,
            average_ticket=average_ticket,
            projection=projection,
            projection_warning=projection_warning,
            elapsed_days=elapsed_days,
            remaining_days=remaining_days,
            configured_working_days=configured_working_days,
            business_holidays=business_holidays,
            total_sold_to_date=total_sold,
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
            gross_revenue_target=gross_revenue_target,
            daily_revenue_target=daily_revenue_target,
            actual_daily_revenue=actual_daily_revenue,
            projection_vs_target=projection_vs_target,
            actual_daily_revenue_vs_target=actual_daily_revenue_vs_target,
        )

    @staticmethod
    def _calculate_total_sold(*, workshop_id: int, selected_month: int, selected_year: int) -> Decimal:
        payments = WorkOrderPaymentMethod.objects.filter(
            workorder__workshop_id=workshop_id,
            workorder__status__in=(WorkOrderStatus.APPROVED, WorkOrderStatus.DRAFT),
            workorder__budget_type="sale",
            due_date__month=selected_month,
            due_date__year=selected_year,
        )
        total = Decimal("0.00")
        for payment in payments:
            total += payment.first_installment_amount.amount + ((payment.installments_count - 1) * payment.remaining_installments_amount.amount)
        return total

    @staticmethod
    def _get_delivered_workorders(*, workshop_id: int, selected_month: int, selected_year: int) -> tuple[list[WorkOrder], list[WorkOrder]]:
        all_workorders = list(
            WorkOrder.objects.filter(
                workshop_id=workshop_id,
                status=WorkOrderStatus.APPROVED,
                delivered_at__month=selected_month,
                delivered_at__year=selected_year,
            )
            .select_related("budget")
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
            )
        )
        profitabilities = []
        for budget in approved_budgets:
            rentability = budget.rentability
            if rentability is not None:
                profitabilities.append(rentability)
        accumulated_profitability = sum(profitabilities) / len(profitabilities) if profitabilities else 0
        return ApprovedBudgetMetrics(
            accumulated_profitability=accumulated_profitability,
            accumulated_markup=calculate_average_markup(approved_budgets),
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
        draft_workorders = list(
            WorkOrder.objects.filter(
                workshop_id=workshop_id,
                status=WorkOrderStatus.DRAFT,
            ).select_related("budget")
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
            )
        )
        total_general = sum((budget.total_budget_value.amount for budget in pending_budgets), Decimal("0.00"))
        monthly = sum(
            (budget.total_budget_value.amount for budget in pending_budgets if budget.entry_date and budget.entry_date.month == selected_month and budget.entry_date.year == selected_year),
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
            )
        )
        return sum((resolve_decimal_amount(budget.display_total_budget_value) for budget in rejected_budgets), Decimal("0.00"))


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
        "filters": {"budget_type__in": ["warranty", "courtesy"], "status": WorkOrderStatus.APPROVED, "budget__reference_budget__isnull": True},
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

    filters = dict(query_config["filters"])
    filters["workshop"] = workshop

    date_field = query_config["date_field"]
    date_filter = {f"{date_field}__month": month, f"{date_field}__year": year}

    if query_config.get("exclude_month"):
        queryset = _build_indicator_queryset(query_config["model"], filters).exclude(**date_filter)
    else:
        if indicator not in ("a_receber_em_execucao", "aguardando_aprovacao"):
            filters.update(date_filter)
        queryset = _build_indicator_queryset(query_config["model"], filters)

    items = list(queryset)
    is_budget_report = query_config["model"] == "budget"
    value_field = query_config["value_field"]

    if value_field is None:
        total_label = f"{len(items)} veículo(s)"
    else:
        total = sum(
            (resolve_decimal_amount(getattr(item, value_field)) for item in items),
            Decimal("0.00"),
        )
        total_label = _format_brl(total)

    return items, is_budget_report, total_label


def _build_indicator_queryset(model_name: str, filters: dict[str, Any]):
    model = Budget if model_name == "budget" else WorkOrder
    queryset = model.objects.filter(**filters)
    if model_name == "budget":
        queryset = queryset.select_related("customer", "vehicle").order_by("entry_date")
    else:
        queryset = queryset.select_related("budget__customer", "budget__vehicle").order_by("criado_em")
    return queryset
