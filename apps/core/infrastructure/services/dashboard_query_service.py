from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.budget.models import Budget, BudgetStatus, BudgetType
from apps.core.domain.services.dashboard_service import DashboardMetrics
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop

logger = logging.getLogger(__name__)

MISSING_WORKSHOP_COST_WARNING = "Para realizar o calculo, cadastre um custo mensal da oficina para o mes selecionado."

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


class DashboardQueryService:
    def compute(
        self,
        workshop: Workshop,
        selected_month: int,
        selected_year: int,
    ) -> DashboardMetrics:
        hoje = timezone.localdate()

        payments_total_sold = list(
            WorkOrderPaymentMethod.objects.filter(
                workorder__workshop=workshop,
                workorder__budget_type="sale",
                due_date__month=selected_month,
                due_date__year=selected_year,
            ).order_by("due_date", "pk")
        )
        total_sold_to_date = sum(
            (resolve_decimal_amount(p.total_paid) for p in payments_total_sold),
            Decimal("0.00"),
        )

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
                        for p in payments_total_sold
                    ],
                },
                ensure_ascii=True,
            ),
        )

        workshop_cost = WorkshopCost.objects.filter(
            workshop=workshop, month=selected_month, year=selected_year
        ).first()

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

        approved_budgets_month = Budget.objects.filter(
            workshop=workshop,
            status=BudgetStatus.APPROVED,
            entry_date__month=selected_month,
            entry_date__year=selected_year,
        )
        profitabilities = [b.rentability for b in approved_budgets_month if b.rentability is not None]

        cars_this_month = (
            WorkOrder.objects.filter(
                workshop=workshop,
                budget_type="sale",
                status=WorkOrderStatus.APPROVED,
                delivered_at__month=selected_month,
                delivered_at__year=selected_year,
                budget__reference_budget__isnull=True,
            ).count()
        )
        warranty_courtesy_cars = (
            WorkOrder.objects.filter(
                workshop=workshop,
                budget_type__in=["warranty", "courtesy"],
                status=WorkOrderStatus.APPROVED,
                delivered_at__month=selected_month,
                delivered_at__year=selected_year,
                budget__reference_budget__isnull=True,
            ).count()
        )
        warranty_count = (
            WorkOrder.objects.filter(
                workshop=workshop,
                budget_type="warranty",
                status=WorkOrderStatus.APPROVED,
                delivered_at__month=selected_month,
                delivered_at__year=selected_year,
            ).count()
        )

        budgets_approval_base = Budget.objects.filter(
            workshop=workshop,
            entry_date__month=selected_month,
            entry_date__year=selected_year,
        ).exclude(budget_type__in=["warranty", "courtesy"])
        budgets_created_this_month = budgets_approval_base.count()
        budgets_approved_this_month = Budget.objects.filter(
            workshop=workshop,
            status=BudgetStatus.APPROVED,
            entry_date__month=selected_month,
            entry_date__year=selected_year,
        ).count()

        pending_budgets_base = Budget.objects.filter(
            workshop=workshop,
            budget_type=BudgetType.SALE,
            status__in=OPEN_BUDGET_STATUSES,
        ).prefetch_related("items", "items__kit_overrides", "items__kit__kit_products", "items__kit__kit_services")

        rejected_budgets = Budget.objects.filter(
            workshop=workshop,
            status__in=REJECTED_BUDGET_STATUS_VALUES,
            entry_date__month=selected_month,
            entry_date__year=selected_year,
        )

        average_ticket = total_sold_to_date / cars_this_month if cars_this_month > 0 else Decimal("0.00")
        accumulated_profitability = sum(profitabilities) / len(profitabilities) if profitabilities else 0
        warranty_return_rate = (warranty_count / cars_this_month) * 100 if cars_this_month > 0 else 0
        approval_rate = (budgets_approved_this_month / budgets_created_this_month) * 100 if budgets_created_this_month > 0 else 0

        draft_workorders = WorkOrder.objects.filter(
            workshop=workshop,
            status=WorkOrderStatus.DRAFT,
        ).prefetch_related("payments")

        total_general_pending_receivable = Decimal("0.00")
        monthly_pending_receivable = Decimal("0.00")
        for workorder in draft_workorders:
            pending_value = resolve_decimal_amount(workorder.pending_payment_value)
            total_general_pending_receivable += pending_value
            if workorder.criado_em and workorder.criado_em.month == selected_month and workorder.criado_em.year == selected_year:
                monthly_pending_receivable += pending_value

        previous_months_pending_receivable = total_general_pending_receivable - monthly_pending_receivable

        total_general_pending_budgets = sum(
            (b.total_budget_value.amount for b in pending_budgets_base), Decimal("0.00")
        )
        monthly_pending_budgets = sum(
            (
                b.total_budget_value.amount
                for b in pending_budgets_base.filter(
                    entry_date__month=selected_month, entry_date__year=selected_year
                )
            ),
            Decimal("0.00"),
        )
        previous_months_pending_budgets = total_general_pending_budgets - monthly_pending_budgets

        total_rejected_budgets = sum(
            getattr(b.display_total_budget_value, "amount", b.display_total_budget_value) or 0
            for b in rejected_budgets
        )

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
            warranty_courtesy_cars=warranty_courtesy_cars,
            average_ticket=average_ticket,
            projection=projection,
            projection_warning=projection_warning,
            elapsed_days=elapsed_days,
            remaining_days=remaining_days,
            configured_working_days=configured_working_days,
            business_holidays=business_holidays,
            total_sold_to_date=total_sold_to_date,
            accumulated_profitability=accumulated_profitability,
            warranty_return_rate=warranty_return_rate,
            approval_rate=approval_rate,
            total_pending_receivable=total_general_pending_receivable,
            total_pending_budgets=total_general_pending_budgets,
            monthly_pending_receivable=monthly_pending_receivable,
            total_general_pending_receivable=total_general_pending_receivable,
            previous_months_pending_receivable=previous_months_pending_receivable,
            total_general_pending_budgets=total_general_pending_budgets,
            monthly_pending_budgets=monthly_pending_budgets,
            previous_months_pending_budgets=previous_months_pending_budgets,
            total_rejected_budgets=total_rejected_budgets,
            gross_revenue_target=gross_revenue_target,
            daily_revenue_target=daily_revenue_target,
            actual_daily_revenue=actual_daily_revenue,
            projection_vs_target=projection_vs_target,
        )


def get_financial_indicator_data(
    workshop: Workshop,
    indicator: str,
    month: int,
    year: int,
) -> tuple[list[Any], bool, str]:
    if indicator == "a_receber_em_execucao":
        workorders = WorkOrder.objects.filter(
            workshop=workshop,
            status=WorkOrderStatus.DRAFT,
        ).prefetch_related("payments", "budget__customer", "budget__vehicle").order_by("criado_em")
        total = sum(resolve_decimal_amount(wo.pending_payment_value) for wo in workorders)
        return list(workorders), False, _format_brl(total)

    if indicator == "a_receber_mes_atual":
        workorders = WorkOrder.objects.filter(
            workshop=workshop,
            status=WorkOrderStatus.DRAFT,
            criado_em__month=month,
            criado_em__year=year,
        ).prefetch_related("payments", "budget__customer", "budget__vehicle").order_by("criado_em")
        total = sum(resolve_decimal_amount(wo.pending_payment_value) for wo in workorders)
        return list(workorders), False, _format_brl(total)

    if indicator == "a_receber_meses_anteriores":
        workorders = WorkOrder.objects.filter(
            workshop=workshop,
            status=WorkOrderStatus.DRAFT,
        ).exclude(
            criado_em__month=month,
            criado_em__year=year,
        ).prefetch_related("payments", "budget__customer", "budget__vehicle").order_by("criado_em")
        total = sum(resolve_decimal_amount(wo.pending_payment_value) for wo in workorders)
        return list(workorders), False, _format_brl(total)

    if indicator == "aguardando_aprovacao":
        budgets = Budget.objects.filter(
            workshop=workshop,
            budget_type=BudgetType.SALE,
            status__in=OPEN_BUDGET_STATUSES,
        ).select_related("customer", "vehicle").order_by("entry_date")
        total = sum(b.total_budget_value.amount for b in budgets)
        return list(budgets), True, _format_brl(total)

    if indicator == "aguardando_aprovacao_mes_atual":
        budgets = Budget.objects.filter(
            workshop=workshop,
            budget_type=BudgetType.SALE,
            status__in=OPEN_BUDGET_STATUSES,
            entry_date__month=month,
            entry_date__year=year,
        ).select_related("customer", "vehicle").order_by("entry_date")
        total = sum(b.total_budget_value.amount for b in budgets)
        return list(budgets), True, _format_brl(total)

    if indicator == "aguardando_aprovacao_meses_anteriores":
        budgets = Budget.objects.filter(
            workshop=workshop,
            budget_type=BudgetType.SALE,
            status__in=OPEN_BUDGET_STATUSES,
        ).exclude(
            entry_date__month=month,
            entry_date__year=year,
        ).select_related("customer", "vehicle").order_by("entry_date")
        total = sum(b.total_budget_value.amount for b in budgets)
        return list(budgets), True, _format_brl(total)

    if indicator == "reprovados":
        budgets = Budget.objects.filter(
            workshop=workshop,
            status__in=REJECTED_BUDGET_STATUS_VALUES,
            entry_date__month=month,
            entry_date__year=year,
        ).select_related("customer", "vehicle").order_by("entry_date")
        total = sum(getattr(b.display_total_budget_value, "amount", b.display_total_budget_value) or 0 for b in budgets)
        return list(budgets), True, _format_brl(total)

    if indicator == "carros_mes":
        workorders = WorkOrder.objects.filter(
            workshop=workshop,
            budget_type="sale",
            status=WorkOrderStatus.APPROVED,
            delivered_at__month=month,
            delivered_at__year=year,
            budget__reference_budget__isnull=True,
        ).select_related("budget__customer", "budget__vehicle").order_by("delivered_at")
        return list(workorders), False, f"{len(workorders)} veículo(s)"

    if indicator == "garantia_cortesia_mes":
        workorders = WorkOrder.objects.filter(
            workshop=workshop,
            budget_type__in=["warranty", "courtesy"],
            status=WorkOrderStatus.APPROVED,
            delivered_at__month=month,
            delivered_at__year=year,
            budget__reference_budget__isnull=True,
        ).select_related("budget__customer", "budget__vehicle").order_by("delivered_at")
        return list(workorders), False, f"{len(workorders)} veículo(s)"

    return [], False, "R$ 0,00"
