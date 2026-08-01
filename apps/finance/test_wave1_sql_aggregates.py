from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget, BudgetType
from apps.core.infrastructure.services.dashboard_query_service import DashboardQueryService
from apps.finance.models.financial_group import FinancialGroup
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.dre import (
    _build_financial_groups_index,
    _resolve_financial_group_for_revenue_movement,
)
from apps.finance.services.reports import build_financial_overview
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Wave1 {suffix}",
        cnpj=f"55.111.222/0001-{suffix:02d}",
        phone="+5511888888888",
        address="Rua Wave1, 100",
    )


class FinancialOverviewSqlAggregateTests(TestCase):
    def test_overview_sums_non_parent_and_workorder_payments(self) -> None:
        workshop = create_workshop(suffix=1)
        payment_method = PaymentMethod.objects.create(workshop=workshop, description="Pix")

        FinancialMovement.objects.create(
            workshop=workshop,
            direction=FinancialMovement.MovementDirection.CREDIT,
            description="Crédito avulso",
            amount=Money(50, "BRL"),
            due_date=date(2026, 6, 10),
            is_paid=True,
        )
        FinancialMovement.objects.create(
            workshop=workshop,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Débito avulso",
            amount=Money(20, "BRL"),
            due_date=date(2026, 6, 10),
            is_paid=True,
        )

        budget = Budget.objects.create(workshop=workshop, entry_date=date(2026, 6, 1))
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            installments_count=2,
            first_installment_amount=Money(100, "BRL"),
            remaining_installments_amount=Money(50, "BRL"),
            due_date=date(2026, 6, 15),
        )
        FinancialMovement.objects.create(
            workshop=workshop,
            workorder=workorder,
            direction=FinancialMovement.MovementDirection.CREDIT,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            description="OS parent",
            amount=Money(0, "BRL"),
            due_date=date(2026, 6, 15),
            is_paid=True,
        )

        overview = build_financial_overview(
            workshop=workshop,
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 30),
        )

        # Manual 50 + WO payment 100+50 = 200 credits; debit 20.
        self.assertEqual(overview.total_credits.amount, Decimal("200.00"))
        self.assertEqual(overview.paid_credits.amount, Decimal("200.00"))
        self.assertEqual(overview.total_debits.amount, Decimal("20.00"))
        self.assertEqual(overview.total_result.amount, Decimal("180.00"))


class DreFinancialGroupsIndexTests(SimpleTestCase):
    def test_resolve_uses_index_without_rescanning_groups(self) -> None:
        vendas = FinancialGroup(pk=1, name="Vendas", parent_id=None, sort_key="01")
        child = FinancialGroup(pk=2, name="Vendas Filhas", parent_id=1, sort_key="01.01")
        receitas = FinancialGroup(pk=3, name="Receitas", parent_id=None, sort_key="02")
        groups = [vendas, child, receitas]
        index = _build_financial_groups_index(groups)

        movement = FinancialMovement(direction=FinancialMovement.MovementDirection.CREDIT)
        resolved = _resolve_financial_group_for_revenue_movement(
            movement=movement,
            financial_groups=groups,
            groups_index=index,
        )
        self.assertIs(resolved, vendas)
        self.assertEqual(index["roots_by_name"]["vendas"], vendas)
        self.assertNotIn("vendas filhas", index["roots_by_name"])


class DashboardDeliveryCountsSqlTests(TestCase):
    def test_delivery_counts_sql_matches_list_path(self) -> None:
        workshop = create_workshop(suffix=2)
        delivered_at = timezone.make_aware(datetime(2026, 6, 15, 12, 0, 0))

        sale = Budget.objects.create(
            workshop=workshop,
            entry_date=date(2026, 6, 1),
            budget_type=BudgetType.SALE,
        )
        warranty = Budget.objects.create(
            workshop=workshop,
            entry_date=date(2026, 6, 3),
            budget_type=BudgetType.WARRANTY,
        )
        courtesy = Budget.objects.create(
            workshop=workshop,
            entry_date=date(2026, 6, 4),
            budget_type=BudgetType.COURTESY,
        )
        sale_ref = Budget.objects.create(
            workshop=workshop,
            entry_date=date(2026, 6, 2),
            budget_type=BudgetType.SALE,
            reference_budget=sale,
        )

        WorkOrder.objects.create(
            workshop=workshop,
            budget=sale,
            status=WorkOrderStatus.APPROVED,
            delivered_at=delivered_at,
        )
        WorkOrder.objects.create(
            workshop=workshop,
            budget=sale_ref,
            status=WorkOrderStatus.APPROVED,
            delivered_at=delivered_at,
        )
        WorkOrder.objects.create(
            workshop=workshop,
            budget=warranty,
            status=WorkOrderStatus.APPROVED,
            delivered_at=delivered_at,
        )
        WorkOrder.objects.create(
            workshop=workshop,
            budget=courtesy,
            status=WorkOrderStatus.APPROVED,
            delivered_at=delivered_at,
        )

        sale_list, warranty_list = DashboardQueryService._get_delivered_workorders(
            workshop_id=workshop.pk,
            selected_month=6,
            selected_year=2026,
        )
        list_counts = DashboardQueryService._compute_delivery_counts(
            sale_workorders=sale_list,
            warranty_workorders=warranty_list,
        )
        sql_counts = DashboardQueryService._compute_delivery_counts_sql(
            workshop_id=workshop.pk,
            selected_month=6,
            selected_year=2026,
        )
        self.assertEqual(sql_counts, list_counts)
        self.assertEqual(sql_counts[0], 1)  # only non-reference sale
        self.assertEqual(sql_counts[1], 2)  # warranty + courtesy without reference
