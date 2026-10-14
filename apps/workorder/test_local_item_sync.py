from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem
from apps.workorder.models import WorkOrder
from apps.workshops.models.workshops import Workshop


class WorkOrderLocalItemSyncTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina de itens locais",
            cnpj="12.345.678/0001-90",
            phone="+5511999999997",
            address="Rua dos Testes, 1",
        )
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 9, 18))

    def test_sync_keeps_local_items_and_their_total(self) -> None:
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            description="Peça avulsa local",
            quantity=2,
            is_local=True,
            local_item_type="product",
            product_selling_price=Money("100.00", "BRL"),
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            description="Serviço avulso local",
            quantity=1,
            is_local=True,
            local_item_type="service",
            service_selling_price=Money("250.00", "BRL"),
        )

        self.budget.refresh_from_db()
        self.budget.refresh_stored_total_amount()
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget)
        workorder.sync_from_budget()
        workorder.refresh_from_db()

        self.assertEqual(workorder.items.filter(is_local=True).count(), 2)
        self.assertEqual(workorder.total_budget_value.amount, Decimal("450.00"))
        self.assertEqual(workorder.stored_total_amount.amount, self.budget.stored_total_amount.amount)
