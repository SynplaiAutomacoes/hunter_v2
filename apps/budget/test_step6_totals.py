from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase
from djmoney.money import Money

from apps.budget.forms.shared import _render_budget_items_rows
from apps.budget.models import Budget, BudgetItem
from apps.budget.review_totals import build_step6_table_totals
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.workshops.models.workshops import Workshop


class BudgetStep6TotalsTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Step6 Totais",
            cnpj="12.345.678/0001-95",
            phone="+5511999999995",
            address="Rua Totais, 1",
        )
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Totais")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="PR-1",
            name="Filtro",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )
        self.service = Service.objects.create(
            workshop=self.workshop,
            name="Troca",
            duration=timedelta(hours=1),
            suggested_cost=Money("40.00", "BRL"),
            selling_price=Money("80.00", "BRL"),
        )
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 8, 24), current_step=6)
        BudgetItem.objects.create(
            budget=self.budget,
            workshop=self.workshop,
            product=self.product,
            quantity=2,
            product_cost_price=Money("10.00", "BRL"),
            product_selling_price=Money("20.00", "BRL"),
        )
        BudgetItem.objects.create(
            budget=self.budget,
            workshop=self.workshop,
            service=self.service,
            quantity=1,
            service_cost_price=Money("40.00", "BRL"),
            service_selling_price=Money("80.00", "BRL"),
            duration=timedelta(hours=1),
        )

    def test_step4_rows_render_origin_badges(self) -> None:
        rows = _render_budget_items_rows(self.budget, step6=False)
        self.assertIn("Avulso", rows["product"])
        self.assertIn("Avulso", rows["service"])

    def test_step6_table_totals_match_displayed_rows(self) -> None:
        totals = build_step6_table_totals(budget=self.budget)

        self.assertEqual(totals["products"].cost, Money("20.00", "BRL"))
        self.assertEqual(totals["products"].sale, Money("40.00", "BRL"))
        self.assertEqual(totals["products"].profit, Money("20.00", "BRL"))
        self.assertEqual(totals["services"].sale, Money("80.00", "BRL"))
