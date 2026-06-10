from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
import json
import logging
from datetime import date
from decimal import Decimal
from typing import Any, TypeVar

from django.db import close_old_connections
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
DASHBOARD_QUERY_MAX_WORKERS = 8
T = TypeVar("T")

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


def count_elapsed_business_days(*, workshop_cost: WorkshopCost, today: date) -> int:
    work_day_dates = workshop_cost.get_work_day_dates()
    return sum(1 for d in work_day_dates if d <= today)


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


def run_dashboard_query_task(task: Callable[[], T]) -> T:
    close_old_connections()
    try:
        return task()
    finally:
        close_old_connections()


@dataclass(frozen=True)
class SoldToDateMetrics:
    payments: list[WorkOrderPaymentMethod]
    total: Decimal


@dataclass(frozen=True)
class ApprovedBudgetMetrics:
    accumulated_profitability: float | Decimal
    accumulated_markup: Decimal
    approved_count: int


@dataclass(frozen=True)
class DeliveredWorkOrderMetrics:
    cars_this_month: int
    cars_this_month_list: list[WorkOrder]
    warranty_courtesy_cars: int
    warranty_courtesy_cars_list: list[WorkOrder]
    warranty_count: int


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


class DashboardQueryService:
    def compute(
        self,
        workshop: Workshop,
        selected_month: int,
        selected_year: int,
    ) -> DashboardMetrics:
        hoje = timezone.localdate()
        workshop_id = workshop.pk

        with ThreadPoolExecutor(max_workers=DASHBOARD_QUERY_MAX_WORKERS, thread_name_prefix="dashboard-query") as executor:
            sold_future = executor.submit(
                run_dashboard_query_task,
                partial(self._get_sold_to_date_metrics, workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year),
            )
            workshop_cost_future = executor.submit(
                run_dashboard_query_task,
                partial(self._get_workshop_cost, workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year),
            )
            approved_budgets_future = executor.submit(
                run_dashboard_query_task,
                partial(self._get_approved_budget_metrics, workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year),
            )
            delivered_workorders_future = executor.submit(
                run_dashboard_query_task,
                partial(self._get_delivered_workorder_metrics, workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year),
            )
            approval_rate_future = executor.submit(
                run_dashboard_query_task,
                partial(self._get_approval_rate_metrics, workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year),
            )
            pending_receivable_future = executor.submit(
                run_dashboard_query_task,
                partial(self._get_pending_receivable_metrics, workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year),
            )
            pending_budgets_future = executor.submit(
                run_dashboard_query_task,
                partial(self._get_pending_budget_metrics, workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year),
            )
            rejected_budgets_future = executor.submit(
                run_dashboard_query_task,
                partial(self._get_rejected_budget_total, workshop_id=workshop_id, selected_month=selected_month, selected_year=selected_year),
            )

            sold_metrics = sold_future.result()
            workshop_cost = workshop_cost_future.result()
            approved_budget_metrics = approved_budgets_future.result()
            delivered_workorder_metrics = delivered_workorders_future.result()
            approval_rate_metrics = approval_rate_future.result()
            pending_receivable_metrics = pending_receivable_future.result()
            pending_budget_metrics = pending_budgets_future.result()
            total_rejected_budgets = rejected_budgets_future.result()

        total_sold_to_date = sold_metrics.total

        logger.info(
            "Dashboard total vendido calculado | %s",
            json.dumps(
                {
                    "workshop_id": workshop.pk,
                    "mes": selected_month,
                    "ano": selected_year,
                    "total_vendido": str(total_sold_to_date),
                    "payments": [
                        {
                            "payment_id": p.pk,
                            "workorder_id": p.workorder_id,
                            "budget_id": getattr(getattr(p.workorder, "budget", None), "pk", None),
                            "due_date": p.due_date.isoformat() if p.due_date else None,
                            "total_paid": str(p.total_paid),
                        }
                        for p in sold_metrics.payments
                    ],
                },
                ensure_ascii=True,
            ),
        )

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
                daily_average = total_sold_to_date / Decimal(elapsed_days)
                projection = (daily_average * Decimal(remaining_days)) + total_sold_to_date
            else:
                projection = total_sold_to_date
        else:
            projection_warning = MISSING_WORKSHOP_COST_WARNING

        cars_this_month = delivered_workorder_metrics.cars_this_month
        average_ticket = total_sold_to_date / cars_this_month if cars_this_month > 0 else Decimal("0.00")
        warranty_return_rate = (delivered_workorder_metrics.warranty_count / (cars_this_month + delivered_workorder_metrics.warranty_count)) * 100 if (cars_this_month + delivered_workorder_metrics.warranty_count) > 0 else 0
        approval_rate = (approval_rate_metrics.approved_count / approval_rate_metrics.created_count) * 100 if approval_rate_metrics.created_count > 0 else 0

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
                actual_daily_revenue = (total_sold_to_date / Decimal(elapsed_days)).quantize(Decimal("0.01"))

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

        return DashboardMetrics(
            workshop_id=workshop.pk,
            selected_month=selected_month,
            selected_year=selected_year,
            months=[(1, "Janeiro"), (2, "Fevereiro"), (3, "Março"), (4, "Abril"), (5, "Maio"), (6, "Junho"), (7, "Julho"), (8, "Agosto"), (9, "Setembro"), (10, "Outubro"), (11, "Novembro"), (12, "Dezembro")],
            years=list(range(hoje.year - 3, hoje.year + 2)),
            cars_this_month=cars_this_month,
            cars_this_month_list=delivered_workorder_metrics.cars_this_month_list,
            warranty_courtesy_cars=delivered_workorder_metrics.warranty_courtesy_cars,
            warranty_courtesy_cars_list=delivered_workorder_metrics.warranty_courtesy_cars_list,
            average_ticket=average_ticket,
            projection=projection,
            projection_warning=projection_warning,
            elapsed_days=elapsed_days,
            remaining_days=remaining_days,
            configured_working_days=configured_working_days,
            business_holidays=business_holidays,
            total_sold_to_date=total_sold_to_date,
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
        )

    def _get_workshop_cost(self, *, workshop_id: int, selected_month: int, selected_year: int) -> WorkshopCost | None:
        return WorkshopCost.objects.filter(workshop_id=workshop_id, month=selected_month, year=selected_year).first()

    def _get_sold_to_date_metrics(self, *, workshop_id: int, selected_month: int, selected_year: int) -> SoldToDateMetrics:
        payments = list(
            WorkOrderPaymentMethod.objects.filter(
                workorder__workshop_id=workshop_id,
                workorder__budget_type="sale",
                due_date__month=selected_month,
                due_date__year=selected_year,
            )
            .select_related("workorder__budget")
            .order_by("due_date", "pk")
        )
        total = sum(
            (resolve_decimal_amount(p.total_paid) for p in payments),
            Decimal("0.00"),
        )
        return SoldToDateMetrics(payments=payments, total=total)

    def _get_approved_budget_metrics(self, *, workshop_id: int, selected_month: int, selected_year: int) -> ApprovedBudgetMetrics:
        approved_budgets = list(
            Budget.objects.filter(
                workshop_id=workshop_id,
                status=BudgetStatus.APPROVED,
                entry_date__month=selected_month,
                entry_date__year=selected_year,
            ).prefetch_related("items", "items__kit_overrides", "items__kit__kit_products", "items__kit__kit_services")
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

    def _get_delivered_workorder_metrics(self, *, workshop_id: int, selected_month: int, selected_year: int) -> DeliveredWorkOrderMetrics:
        sale_workorders = list(
            WorkOrder.objects.filter(
                workshop_id=workshop_id,
                budget_type="sale",
                status=WorkOrderStatus.APPROVED,
                delivered_at__month=selected_month,
                delivered_at__year=selected_year,
            )
            .select_related("budget__customer", "budget__vehicle")
            .prefetch_related("items", "items__kit_overrides", "items__kit__kit_products", "items__kit__kit_services")
            .order_by("delivered_at")
        )
        warranty_courtesy_workorders = list(
            WorkOrder.objects.filter(
                workshop_id=workshop_id,
                budget_type__in=["warranty", "courtesy"],
                status=WorkOrderStatus.APPROVED,
                delivered_at__month=selected_month,
                delivered_at__year=selected_year,
            )
            .select_related("budget__customer", "budget__vehicle")
            .prefetch_related("items", "items__kit_overrides", "items__kit__kit_products", "items__kit__kit_services")
            .order_by("delivered_at")
        )

        return DeliveredWorkOrderMetrics(
            cars_this_month=sum(1 for workorder in sale_workorders if workorder.budget.reference_budget_id is None),
            cars_this_month_list=sale_workorders,
            warranty_courtesy_cars=sum(1 for workorder in warranty_courtesy_workorders if workorder.budget.reference_budget_id is None),
            warranty_courtesy_cars_list=warranty_courtesy_workorders,
            warranty_count=sum(1 for workorder in warranty_courtesy_workorders if workorder.budget_type == "warranty"),
        )

    def _get_approval_rate_metrics(self, *, workshop_id: int, selected_month: int, selected_year: int) -> ApprovalRateMetrics:
        budgets_created_this_month = (
            Budget.objects.filter(
                workshop_id=workshop_id,
                entry_date__month=selected_month,
                entry_date__year=selected_year,
            )
            .exclude(budget_type__in=["warranty", "courtesy"])
            .exclude(status=BudgetStatus.CANCELLED)
            .count()
        )
        budgets_approved_this_month = Budget.objects.filter(
            workshop_id=workshop_id,
            status=BudgetStatus.APPROVED,
            entry_date__month=selected_month,
            entry_date__year=selected_year,
        ).count()
        return ApprovalRateMetrics(created_count=budgets_created_this_month, approved_count=budgets_approved_this_month)

    def _get_pending_receivable_metrics(self, *, workshop_id: int, selected_month: int, selected_year: int) -> PendingReceivableMetrics:
        draft_workorders = list(
            WorkOrder.objects.filter(
                workshop_id=workshop_id,
                status=WorkOrderStatus.DRAFT,
            )
            .select_related("budget")
            .prefetch_related("payments", "items", "items__kit_overrides", "items__kit__kit_products", "items__kit__kit_services")
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

    def _get_pending_budget_metrics(self, *, workshop_id: int, selected_month: int, selected_year: int) -> PendingBudgetMetrics:
        pending_budgets = list(
            Budget.objects.filter(
                workshop_id=workshop_id,
                budget_type=BudgetType.SALE,
                status__in=OPEN_BUDGET_STATUSES,
            ).prefetch_related("items", "items__kit_overrides", "items__kit__kit_products", "items__kit__kit_services")
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

    def _get_rejected_budget_total(self, *, workshop_id: int, selected_month: int, selected_year: int) -> Decimal:
        rejected_budgets = list(
            Budget.objects.filter(
                workshop_id=workshop_id,
                status__in=REJECTED_BUDGET_STATUS_VALUES,
                entry_date__month=selected_month,
                entry_date__year=selected_year,
            ).prefetch_related("items", "items__kit_overrides", "items__kit__kit_products", "items__kit__kit_services")
        )
        return sum((resolve_decimal_amount(budget.display_total_budget_value) for budget in rejected_budgets), Decimal("0.00"))


def get_financial_indicator_data(
    workshop: Workshop,
    indicator: str,
    month: int,
    year: int,
) -> tuple[list[Any], bool, str]:
    if indicator == "a_receber_em_execucao":
        workorders = (
            WorkOrder.objects.filter(
                workshop=workshop,
                status=WorkOrderStatus.DRAFT,
            )
            .prefetch_related("payments", "budget__customer", "budget__vehicle")
            .order_by("criado_em")
        )
        total = sum(resolve_decimal_amount(wo.pending_payment_value) for wo in workorders)
        return list(workorders), False, _format_brl(total)

    if indicator == "a_receber_mes_atual":
        workorders = (
            WorkOrder.objects.filter(
                workshop=workshop,
                status=WorkOrderStatus.DRAFT,
                criado_em__month=month,
                criado_em__year=year,
            )
            .prefetch_related("payments", "budget__customer", "budget__vehicle")
            .order_by("criado_em")
        )
        total = sum(resolve_decimal_amount(wo.pending_payment_value) for wo in workorders)
        return list(workorders), False, _format_brl(total)

    if indicator == "a_receber_meses_anteriores":
        workorders = (
            WorkOrder.objects.filter(
                workshop=workshop,
                status=WorkOrderStatus.DRAFT,
            )
            .exclude(
                criado_em__month=month,
                criado_em__year=year,
            )
            .prefetch_related("payments", "budget__customer", "budget__vehicle")
            .order_by("criado_em")
        )
        total = sum(resolve_decimal_amount(wo.pending_payment_value) for wo in workorders)
        return list(workorders), False, _format_brl(total)

    if indicator == "aguardando_aprovacao":
        budgets = (
            Budget.objects.filter(
                workshop=workshop,
                budget_type=BudgetType.SALE,
                status__in=OPEN_BUDGET_STATUSES,
            )
            .select_related("customer", "vehicle")
            .order_by("entry_date")
        )
        total = sum(b.total_budget_value.amount for b in budgets)
        return list(budgets), True, _format_brl(total)

    if indicator == "aguardando_aprovacao_mes_atual":
        budgets = (
            Budget.objects.filter(
                workshop=workshop,
                budget_type=BudgetType.SALE,
                status__in=OPEN_BUDGET_STATUSES,
                entry_date__month=month,
                entry_date__year=year,
            )
            .select_related("customer", "vehicle")
            .order_by("entry_date")
        )
        total = sum(b.total_budget_value.amount for b in budgets)
        return list(budgets), True, _format_brl(total)

    if indicator == "aguardando_aprovacao_meses_anteriores":
        budgets = (
            Budget.objects.filter(
                workshop=workshop,
                budget_type=BudgetType.SALE,
                status__in=OPEN_BUDGET_STATUSES,
            )
            .exclude(
                entry_date__month=month,
                entry_date__year=year,
            )
            .select_related("customer", "vehicle")
            .order_by("entry_date")
        )
        total = sum(b.total_budget_value.amount for b in budgets)
        return list(budgets), True, _format_brl(total)

    if indicator == "reprovados":
        budgets = (
            Budget.objects.filter(
                workshop=workshop,
                status__in=REJECTED_BUDGET_STATUS_VALUES,
                entry_date__month=month,
                entry_date__year=year,
            )
            .select_related("customer", "vehicle")
            .order_by("entry_date")
        )
        total = sum(getattr(b.display_total_budget_value, "amount", b.display_total_budget_value) or 0 for b in budgets)
        return list(budgets), True, _format_brl(total)

    if indicator == "carros_mes":
        workorders = (
            WorkOrder.objects.filter(
                workshop=workshop,
                budget_type="sale",
                status=WorkOrderStatus.APPROVED,
                delivered_at__month=month,
                delivered_at__year=year,
                budget__reference_budget__isnull=True,
            )
            .select_related("budget__customer", "budget__vehicle")
            .order_by("delivered_at")
        )
        return list(workorders), False, f"{len(workorders)} veículo(s)"

    if indicator == "garantia_cortesia_mes":
        workorders = (
            WorkOrder.objects.filter(
                workshop=workshop,
                budget_type__in=["warranty", "courtesy"],
                status=WorkOrderStatus.APPROVED,
                delivered_at__month=month,
                delivered_at__year=year,
                budget__reference_budget__isnull=True,
            )
            .select_related("budget__customer", "budget__vehicle")
            .order_by("delivered_at")
        )
        return list(workorders), False, f"{len(workorders)} veículo(s)"

    return [], False, "R$ 0,00"
