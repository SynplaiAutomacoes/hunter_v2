from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem, BudgetItemBenefitType, BudgetItemLocalType
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

    def test_mixed_benefit_items_are_abatidos_only_in_summary(self) -> None:
        product_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            is_local=True,
            local_item_type=BudgetItemLocalType.PRODUCT,
            description="Produto garantia",
            quantity=1,
            product_cost_price=Money("10.00", "BRL"),
            product_selling_price=Money("20.00", "BRL"),
            shipping=Money("30.00", "BRL"),
        )
        product_item.item_benefit_type = BudgetItemBenefitType.WARRANTY
        product_item.save(update_fields=["item_benefit_type"])
        product_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            is_local=True,
            local_item_type=BudgetItemLocalType.SERVICE,
            description="Servico cobrado",
            quantity=2,
            service_cost_price=Money("1.00", "BRL"),
            service_selling_price=Money("2.37", "BRL"),
            duration=timedelta(minutes=30),
        )

        self.assertEqual(self.budget.selected_items_total_products_without_shipping, Money("20.00", "BRL"))
        self.assertEqual(self.budget.selected_items_total_services_value, Money("4.74", "BRL"))
        self.assertEqual(self.budget.selected_items_total_shipping_value, Money("30.00", "BRL"))
        self.assertEqual(self.budget.summary_total_before_benefit_value, Money("54.74", "BRL"))
        self.assertEqual(self.budget.benefit_summary_label, "Garantia")
        self.assertEqual(self.budget.benefit_summary_total_value, Money("50.00", "BRL"))
        self.assertEqual(self.budget.summary_amount_due_value, Money("4.74", "BRL"))

    def test_fixed_budget_abates_all_items_in_summary(self) -> None:
        self.budget.budget_type = "warranty"
        self.budget.save(update_fields=["budget_type"])

        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            is_local=True,
            local_item_type=BudgetItemLocalType.PRODUCT,
            description="Produto garantia",
            quantity=1,
            product_cost_price=Money("10.00", "BRL"),
            product_selling_price=Money("20.00", "BRL"),
            shipping=Money("30.00", "BRL"),
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            is_local=True,
            local_item_type=BudgetItemLocalType.SERVICE,
            description="Servico garantia",
            quantity=2,
            service_cost_price=Money("1.00", "BRL"),
            service_selling_price=Money("2.37", "BRL"),
            duration=timedelta(minutes=30),
        )

        self.assertEqual(self.budget.summary_total_before_benefit_value, Money("54.74", "BRL"))
        self.assertEqual(self.budget.benefit_summary_total_value, Money("54.74", "BRL"))
        self.assertEqual(self.budget.summary_amount_due_value, Money("0.00", "BRL"))
