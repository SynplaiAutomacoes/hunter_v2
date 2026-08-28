from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from djmoney.money import Money

from apps.budget.forms.shared import _render_budget_items_rows
from apps.budget.item_origin import AVULSO_ORIGIN_LABEL, KIT_ORIGIN_LABEL
from apps.budget.models import Budget, BudgetItem
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.workshops.models.workshops import Workshop

STEP6_LAYOUT_PATH = Path(__file__).resolve().parent / "forms" / "layouts" / "step6.py"


class BudgetStep6OriginTemplateTests(SimpleTestCase):
    def test_step6_layout_includes_origin_column(self) -> None:
        layout = STEP6_LAYOUT_PATH.read_text(encoding="utf-8")
        self.assertIn("ORIGEM", layout)
        self.assertGreaterEqual(layout.count("ORIGEM"), 2)


class BudgetStep6OriginDisplayTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Step6 Origem",
            cnpj="12.345.678/0001-94",
            phone="+5511999999994",
            address="Rua Origem, 1",
        )
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Origem")
        self.avulso_product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="AV-1",
            name="Filtro Avulso",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )
        self.kit_product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="KT-1",
            name="Oleo Do Kit",
            unit=Product.Unit.UND,
            cost_price=Money("15.00", "BRL"),
            selling_price=Money("30.00", "BRL"),
        )
        self.kit_service = Service.objects.create(
            workshop=self.workshop,
            name="Troca Do Kit",
            duration=timedelta(hours=1),
            suggested_cost=Money("40.00", "BRL"),
            selling_price=Money("80.00", "BRL"),
        )
        self.kit = Kit.objects.create(workshop=self.workshop, name="Kit Revisao 10k")
        self.kit.refresh_from_db()
        KitProduct.objects.create(kit=self.kit, product=self.kit_product, quantity=2)
        KitService.objects.create(kit=self.kit, service=self.kit_service, quantity=1, duration=timedelta(hours=1))
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 8, 24), current_step=6)
        BudgetItem.objects.create(
            budget=self.budget,
            workshop=self.workshop,
            product=self.avulso_product,
            quantity=1,
            product_cost_price=Money("10.00", "BRL"),
            product_selling_price=Money("20.00", "BRL"),
        )
        BudgetItem.objects.create(
            budget=self.budget,
            workshop=self.workshop,
            kit=self.kit,
            quantity=1,
        )

    def test_step6_rows_render_avulso_and_kit_origin_badges(self) -> None:
        rows = _render_budget_items_rows(self.budget, step6=True)
        products_html = rows["product"]
        services_html = rows["service"]

        self.assertIn(AVULSO_ORIGIN_LABEL, products_html)
        self.assertIn(KIT_ORIGIN_LABEL, products_html)
        self.assertIn(KIT_ORIGIN_LABEL, services_html)
        self.assertIn(self.kit.name, products_html)
        self.assertIn(reverse("catalog:kits_update", kwargs={"pk": self.kit.pk}), products_html)
