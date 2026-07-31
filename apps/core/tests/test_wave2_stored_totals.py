from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from djmoney.money import Money

from apps.budget.models import Budget, BudgetStatus, BudgetType
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.core.infrastructure.services.dashboard_query_service import DashboardQueryService
from apps.finance.models.payment_method import PaymentMethod
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Wave2 {suffix}",
        cnpj=f"66.333.444/0001-{suffix:02d}",
        phone="+5511777777777",
        address="Rua Wave2, 200",
    )


class StoredTotalsWritePathTests(TestCase):
    def test_budget_item_updates_stored_total(self) -> None:
        from apps.budget.models import BudgetItem

        workshop = create_workshop(suffix=1)
        group = CatalogGroup.objects.create(workshop=workshop, name="Grupo Wave2")
        product = Product.objects.create(
            workshop=workshop,
            group=group,
            name="Peca Wave2",
            cost_price=Money(10, "BRL"),
            selling_price=Money(100, "BRL"),
        )
        budget = Budget.objects.create(
            workshop=workshop,
            entry_date=date(2026, 6, 1),
            budget_type=BudgetType.SALE,
            status=BudgetStatus.DRAFT,
        )
        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            product=product,
            quantity=1,
        )
        budget.refresh_from_db()
        self.assertGreater(budget.stored_total_amount.amount, Decimal("0.00"))
        self.assertEqual(budget.stored_total_amount.amount, budget.total_budget_value.amount)

    def test_workorder_payment_updates_stored_paid(self) -> None:
        workshop = create_workshop(suffix=2)
        payment_method = PaymentMethod.objects.create(workshop=workshop, description="Pix")
        budget = Budget.objects.create(workshop=workshop, entry_date=date(2026, 6, 1))
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.DRAFT)
        workorder.refresh_stored_total_amount()
        WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            installments_count=1,
            first_installment_amount=Money(40, "BRL"),
            remaining_installments_amount=Money(0, "BRL"),
            due_date=date(2026, 6, 15),
        )
        workorder.refresh_from_db()
        self.assertEqual(workorder.stored_paid_amount.amount, Decimal("40.00"))


class DashboardPendingAggregateTests(TestCase):
    def test_pending_budget_metrics_use_stored_total_without_pricing_queries(self) -> None:
        workshop = create_workshop(suffix=3)
        budget = Budget.objects.create(
            workshop=workshop,
            entry_date=date(2026, 6, 10),
            budget_type=BudgetType.SALE,
            status=BudgetStatus.DRAFT,
        )
        Budget.objects.filter(pk=budget.pk).update(stored_total_amount=Money(250, "BRL"))

        with CaptureQueriesContext(connection) as ctx:
            metrics = DashboardQueryService._get_pending_budget_metrics(
                workshop_id=workshop.pk,
                selected_month=6,
                selected_year=2026,
            )

        self.assertEqual(metrics.total_general, Decimal("250.00"))
        self.assertEqual(metrics.monthly, Decimal("250.00"))
        # Aggregate path should be a single SUM query (no item prefetch).
        self.assertEqual(len(ctx), 1)

    def test_pending_receivable_uses_stored_total_minus_paid(self) -> None:
        workshop = create_workshop(suffix=4)
        budget = Budget.objects.create(workshop=workshop, entry_date=date(2026, 6, 1))
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.DRAFT)
        WorkOrder.objects.filter(pk=workorder.pk).update(
            stored_total_amount=Money(100, "BRL"),
            stored_paid_amount=Money(30, "BRL"),
        )

        metrics = DashboardQueryService._get_pending_receivable_metrics(
            workshop_id=workshop.pk,
            selected_month=workorder.criado_em.month,
            selected_year=workorder.criado_em.year,
        )
        self.assertEqual(metrics.total_general, Decimal("70.00"))
        self.assertEqual(metrics.monthly, Decimal("70.00"))

    def test_rejected_budget_total_uses_stored_amount(self) -> None:
        workshop = create_workshop(suffix=5)
        budget = Budget.objects.create(
            workshop=workshop,
            entry_date=date(2026, 6, 12),
            budget_type=BudgetType.SALE,
            status=BudgetStatus.REJECTED,
        )
        Budget.objects.filter(pk=budget.pk).update(stored_total_amount=Money(80, "BRL"))

        total = DashboardQueryService._get_rejected_budget_total(
            workshop_id=workshop.pk,
            selected_month=6,
            selected_year=2026,
        )
        self.assertEqual(total, Decimal("80.00"))
