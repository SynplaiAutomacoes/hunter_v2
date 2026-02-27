from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Budget {suffix}",
        cnpj=f"11.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


def create_budget(*, workshop: Workshop) -> Budget:
    budget = Budget(workshop=workshop, entry_date=timezone.now().date())
    budget.save()
    return budget


class BudgetTotalsConsistencyTests(TestCase):
    def test_total_base_value_uses_item_selling_totals_only(self) -> None:
        workshop = create_workshop(suffix=71)
        budget = create_budget(workshop=workshop)

        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Peca local",
            quantity=2,
            product_cost_price=Money("50.00", "BRL"),
            product_selling_price=Money("100.00", "BRL"),
            shipping=Money("5.00", "BRL"),
        )
        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Servico local",
            quantity=1,
            service_cost_price=Money("0.00", "BRL"),
            service_selling_price=Money("0.01", "BRL"),
        )

        with patch.object(Budget, "calculate_pricing_methods", side_effect=AssertionError("Nao deve usar metodo de precificacao para total_base_value")):
            self.assertEqual(budget.total_products_value, Money("205.00", "BRL"))
            self.assertEqual(budget.total_services_value, Money("0.01", "BRL"))
            self.assertEqual(budget.total_base_value, Money("205.01", "BRL"))

    def test_total_budget_value_applies_discount_over_item_totals(self) -> None:
        workshop = create_workshop(suffix=72)
        budget = create_budget(workshop=workshop)

        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Servico local",
            quantity=1,
            service_selling_price=Money("0.01", "BRL"),
        )

        budget.discount_value = Money(Decimal("0.01"), "BRL")
        budget.save(update_fields=["discount_value"])

        self.assertEqual(budget.total_base_value, Money("0.01", "BRL"))
        self.assertEqual(budget.total_budget_value, Money("0.00", "BRL"))
