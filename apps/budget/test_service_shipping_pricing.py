from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem, BudgetItemLocalType
from apps.catalog.models.services import Service
from apps.workshops.models.workshops import Workshop


class BudgetServiceShippingPricingTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Frete Servico",
            cnpj="55.222.333/0001-01",
            phone="+5511999999999",
            address="Rua Teste, 123",
        )
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 1),
            current_step=4,
        )

    def test_catalog_service_shipping_counts_in_budget_totals(self) -> None:
        service = Service.objects.create(
            workshop=self.workshop,
            name="Guincho terceirizado",
            duration=timedelta(hours=1),
            suggested_cost=Money("50.00", "BRL"),
            selling_price=Money("100.00", "BRL"),
            shipping=Money("15.00", "BRL"),
        )

        item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            service=service,
            quantity=2,
        )

        item.refresh_from_db()
        self.assertEqual(item.service_shipping, Money("15.00", "BRL"))
        self.assertEqual(self.budget.total_services_shipping, Money("30.00", "BRL"))
        self.assertEqual(self.budget.total_shipping, Money("30.00", "BRL"))
        self.assertEqual(self.budget.total_services_value, Money("230.00", "BRL"))
        self.assertEqual(self.budget.selected_items_total_base_value, Money("230.00", "BRL"))

    def test_local_service_shipping_counts_in_budget_totals(self) -> None:
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            is_local=True,
            local_item_type=BudgetItemLocalType.SERVICE,
            description="Frete servico local",
            quantity=2,
            service_cost_price=Money("50.00", "BRL"),
            service_selling_price=Money("100.00", "BRL"),
            service_shipping=Money("15.00", "BRL"),
            duration=timedelta(hours=1),
        )

        self.assertEqual(self.budget.total_services_shipping, Money("30.00", "BRL"))
        self.assertEqual(self.budget.total_shipping, Money("30.00", "BRL"))
        self.assertEqual(self.budget.total_services_value, Money("230.00", "BRL"))
        self.assertEqual(self.budget.selected_items_total_base_value, Money("230.00", "BRL"))
