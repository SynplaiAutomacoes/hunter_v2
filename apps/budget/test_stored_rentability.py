from __future__ import annotations

from datetime import date

from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetStatus
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.workshops.models.workshops import Workshop


class BudgetStoredRentabilityTests(TestCase):
    def test_refresh_persists_gestor_pdf_rentability(self) -> None:
        workshop = Workshop.objects.create(
            name="Oficina Rentabilidade",
            cnpj="11.222.333/0001-44",
            phone="+5511999990000",
            address="Rua Rent, 1",
        )
        group = CatalogGroup.objects.create(workshop=workshop, name="Grupo Rent")
        product = Product.objects.create(
            workshop=workshop,
            group=group,
            name="Peca Rent",
            cost_price=Money(80, "BRL"),
            selling_price=Money(120, "BRL"),
        )
        budget = Budget.objects.create(
            workshop=workshop,
            status=BudgetStatus.DRAFT,
            entry_date=date(2026, 8, 15),
            stored_total_amount=Money(120, "BRL"),
        )
        from apps.budget.models import BudgetItem

        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=1)
        budget.refresh_from_db()
        budget.refresh_stored_rentability()
        self.assertIsNotNone(budget.stored_rentability)
        self.assertEqual(budget.rentability, budget.stored_rentability)
        self.assertEqual(budget.rentability, budget.compute_gestor_pdf_rentability())
