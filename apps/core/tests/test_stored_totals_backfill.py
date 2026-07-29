from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.core.infrastructure.services.stored_totals import backfill_stored_totals
from apps.finance.models.payment_method import PaymentMethod
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderPaymentMethod
from apps.workshops.models.workshops import Workshop


class StoredTotalsBackfillTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Backfill",
            cnpj="68.333.444/0001-01",
            phone="+5511767676767",
            address="Rua Backfill, 100",
        )
        group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Backfill")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=group,
            code="BACKFILL-1",
            name="Peça Backfill",
            cost_price=Money(20, "BRL"),
            selling_price=Money(100, "BRL"),
        )
        self.second_product = Product.objects.create(
            workshop=self.workshop,
            group=group,
            code="BACKFILL-2",
            name="Peça Fracionária Backfill",
            cost_price=Money("2.25", "BRL"),
            selling_price=Money("10.25", "BRL"),
        )

    def test_rebuilds_bulk_created_budget_and_workorder_totals_idempotently(self) -> None:
        budget = Budget(workshop=self.workshop, entry_date=date(2026, 7, 1))
        Budget.objects.bulk_create([budget])
        BudgetItem.objects.bulk_create(
            [
                BudgetItem(
                    workshop=self.workshop,
                    budget=budget,
                    product=self.product,
                    quantity=2,
                    product_cost_price=Money(20, "BRL"),
                    product_selling_price=Money(100, "BRL"),
                    shipping=Money(5, "BRL"),
                ),
                BudgetItem(
                    workshop=self.workshop,
                    budget=budget,
                    product=self.second_product,
                    quantity=3,
                    product_cost_price=Money("2.25", "BRL"),
                    product_selling_price=Money("10.25", "BRL"),
                ),
            ]
        )

        workorder = WorkOrder(workshop=self.workshop, budget=budget)
        WorkOrder.objects.bulk_create([workorder])
        WorkOrderItem.objects.bulk_create(
            [
                WorkOrderItem(
                    workshop=self.workshop,
                    workorder=workorder,
                    product=self.product,
                    quantity=2,
                    product_cost_price=Money(20, "BRL"),
                    product_selling_price=Money(100, "BRL"),
                    shipping=Money(5, "BRL"),
                ),
                WorkOrderItem(
                    workshop=self.workshop,
                    workorder=workorder,
                    product=self.second_product,
                    quantity=3,
                    product_cost_price=Money("2.25", "BRL"),
                    product_selling_price=Money("10.25", "BRL"),
                ),
            ]
        )
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix Backfill")
        WorkOrderPaymentMethod.objects.bulk_create(
            [
                WorkOrderPaymentMethod(
                    workorder=workorder,
                    payment_method=payment_method,
                    installments_count=2,
                    first_installment_amount=Money("40.25", "BRL"),
                    remaining_installments_amount=Money("10.10", "BRL"),
                    due_date=date(2026, 7, 10),
                )
            ]
        )
        Budget.objects.filter(pk=budget.pk).update(stored_total_amount=Money(0, "BRL"))
        WorkOrder.objects.filter(pk=workorder.pk).update(
            stored_total_amount=Money(0, "BRL"),
            stored_paid_amount=Money(0, "BRL"),
        )

        first_result = backfill_stored_totals(batch_size=1, workshop_id=self.workshop.pk)
        budget.refresh_from_db()
        workorder.refresh_from_db()
        first_values = (
            budget.stored_total_amount.amount,
            workorder.stored_total_amount.amount,
            workorder.stored_paid_amount.amount,
        )

        second_result = backfill_stored_totals(batch_size=1, workshop_id=self.workshop.pk)
        budget.refresh_from_db()
        workorder.refresh_from_db()

        self.assertEqual(first_result.budgets_scanned, 1)
        self.assertEqual(first_result.workorders_scanned, 1)
        self.assertEqual(first_values, (Decimal("235.75"), Decimal("235.75"), Decimal("50.35")))
        self.assertEqual(first_result.budgets_updated, 1)
        self.assertEqual(first_result.workorders_updated, 1)
        self.assertEqual(second_result.budgets_scanned, 1)
        self.assertEqual(second_result.budgets_updated, 0)
        self.assertEqual(second_result.workorders_scanned, 1)
        self.assertEqual(second_result.workorders_updated, 0)
        self.assertEqual(budget.stored_total_amount.currency.code, "BRL")
        self.assertEqual(workorder.stored_total_amount.currency.code, "BRL")
        self.assertEqual(workorder.stored_paid_amount.currency.code, "BRL")
        self.assertEqual(
            (
                budget.stored_total_amount.amount,
                workorder.stored_total_amount.amount,
                workorder.stored_paid_amount.amount,
            ),
            first_values,
        )

    def test_preserves_zero_brl_totals_when_records_have_no_items_or_payments(self) -> None:
        budget = Budget(workshop=self.workshop, entry_date=date(2026, 7, 2))
        Budget.objects.bulk_create([budget])
        workorder = WorkOrder(workshop=self.workshop, budget=budget)
        WorkOrder.objects.bulk_create([workorder])

        result = backfill_stored_totals(workshop_id=self.workshop.pk)
        budget.refresh_from_db()
        workorder.refresh_from_db()

        self.assertEqual(result.budgets_scanned, 1)
        self.assertEqual(result.budgets_updated, 0)
        self.assertEqual(result.workorders_scanned, 1)
        self.assertEqual(result.workorders_updated, 0)
        self.assertEqual(budget.stored_total_amount, Money(0, "BRL"))
        self.assertEqual(workorder.stored_total_amount, Money(0, "BRL"))
        self.assertEqual(workorder.stored_paid_amount, Money(0, "BRL"))

    def test_backfill_uses_operational_total_for_fixed_warranty_budget(self) -> None:
        from apps.budget.models import BudgetType

        budget = Budget(workshop=self.workshop, entry_date=date(2026, 7, 3), budget_type=BudgetType.WARRANTY)
        Budget.objects.bulk_create([budget])
        BudgetItem.objects.bulk_create(
            [
                BudgetItem(
                    workshop=self.workshop,
                    budget=budget,
                    product=self.product,
                    quantity=1,
                    product_cost_price=Money(20, "BRL"),
                    product_selling_price=Money(100, "BRL"),
                    shipping=Money(5, "BRL"),
                    item_benefit_type="warranty",
                ),
            ]
        )
        workorder = WorkOrder(workshop=self.workshop, budget=budget, budget_type="warranty")
        WorkOrder.objects.bulk_create([workorder])
        WorkOrderItem.objects.bulk_create(
            [
                WorkOrderItem(
                    workshop=self.workshop,
                    workorder=workorder,
                    product=self.product,
                    quantity=1,
                    product_cost_price=Money(20, "BRL"),
                    product_selling_price=Money(100, "BRL"),
                    shipping=Money(5, "BRL"),
                    item_benefit_type="warranty",
                ),
            ]
        )
        Budget.objects.filter(pk=budget.pk).update(stored_total_amount=Money(0, "BRL"))
        WorkOrder.objects.filter(pk=workorder.pk).update(stored_total_amount=Money(0, "BRL"))

        result = backfill_stored_totals(workshop_id=self.workshop.pk, budget_types={"warranty", "courtesy"})
        budget.refresh_from_db()
        workorder.refresh_from_db()

        self.assertEqual(result.budgets_updated, 1)
        self.assertEqual(result.workorders_updated, 1)
        self.assertEqual(budget.stored_total_amount.amount, Decimal("105.00"))
        self.assertEqual(workorder.stored_total_amount.amount, Decimal("105.00"))
        self.assertEqual(budget.total_budget_value.amount, Decimal("0.00"))
        self.assertEqual(workorder.total_budget_value.amount, Decimal("0.00"))

    def test_budget_types_filter_skips_sale_documents(self) -> None:
        from apps.budget.models import BudgetType

        sale = Budget(workshop=self.workshop, entry_date=date(2026, 7, 4), budget_type=BudgetType.SALE)
        warranty = Budget(workshop=self.workshop, entry_date=date(2026, 7, 4), budget_type=BudgetType.WARRANTY)
        Budget.objects.bulk_create([sale, warranty])
        BudgetItem.objects.bulk_create(
            [
                BudgetItem(
                    workshop=self.workshop,
                    budget=warranty,
                    product=self.product,
                    quantity=1,
                    product_selling_price=Money(50, "BRL"),
                    item_benefit_type="warranty",
                ),
            ]
        )
        Budget.objects.filter(pk__in=[sale.pk, warranty.pk]).update(stored_total_amount=Money(0, "BRL"))

        result = backfill_stored_totals(workshop_id=self.workshop.pk, budget_types={"warranty"})
        sale.refresh_from_db()
        warranty.refresh_from_db()

        self.assertEqual(result.budgets_scanned, 1)
        self.assertEqual(result.budgets_updated, 1)
        self.assertEqual(sale.stored_total_amount.amount, Decimal("0.00"))
        self.assertEqual(warranty.stored_total_amount.amount, Decimal("50.00"))

    def test_rejects_non_positive_batch_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            backfill_stored_totals(batch_size=0)
