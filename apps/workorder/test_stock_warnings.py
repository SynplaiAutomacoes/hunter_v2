from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetStatus
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.product_issues import annotate_product_issues
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


class AnnotateProductIssuesStockCheckTests(SimpleTestCase):
    def test_check_stock_false_skips_shortage_warnings(self) -> None:
        product = SimpleNamespace(id=1, pk=1, name="Coxim", description="Coxim", ncm="12345678")
        item = SimpleNamespace(
            product_id=1,
            product=product,
            quantity=5,
            description="Coxim",
            is_customer_supplied=False,
            entity_id=1,
        )

        summary = annotate_product_issues(workshop=SimpleNamespace(pk=1), items=[item], check_stock=False)

        self.assertFalse(summary.has_stock_issues)
        self.assertEqual(item.excess_quantity, 0)
        self.assertFalse(item.has_product_issues)


class WorkOrderFinalizedStockWarningTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Stock Warning",
            cnpj="98.765.432/0001-10",
            phone="+5511888888888",
            address="Rua Estoque, 10",
            uf="SP",
        )
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Stock Warning")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="STK-1",
            name="Peca Sem Estoque",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            ncm="12345678",
        )
        stock = self.product.stock_products
        stock.current_quantity = 0
        stock.save(update_fields=["current_quantity"])

        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 8, 10),
            status=BudgetStatus.APPROVED,
            current_step=6,
        )
        self.workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            status=WorkOrderStatus.DRAFT,
            budget_type="sale",
        )
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            product=self.product,
            quantity=2,
        )

    def test_draft_workorder_shows_stock_issues_when_quantity_exceeds_stock(self) -> None:
        self.assertTrue(self.workorder.has_stock_issues)

    def test_delivered_workorder_hides_stock_issues(self) -> None:
        self.workorder.status = WorkOrderStatus.APPROVED
        self.workorder._skip_stock_consumption_guard = True
        self.workorder.save(update_fields=["status"])
        self.workorder.invalidate_pricing_snapshot_cache()

        self.assertTrue(self.workorder.is_status_locked)
        self.assertFalse(self.workorder.has_stock_issues)

        product_lines = list(self.workorder.pricing_snapshot.product_lines)
        self.assertTrue(product_lines)
        for line in product_lines:
            self.assertEqual(getattr(line, "excess_quantity", 0), 0)
            self.assertFalse(getattr(line, "has_product_issues", False))

    def test_cancelled_workorder_hides_stock_issues(self) -> None:
        WorkOrder.objects.filter(pk=self.workorder.pk).update(status=WorkOrderStatus.CANCELLED)
        self.workorder.refresh_from_db()
        self.workorder.invalidate_pricing_snapshot_cache()

        self.assertFalse(self.workorder.has_stock_issues)
