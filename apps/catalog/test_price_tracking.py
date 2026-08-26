from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.price_tracking import apply_product_import_prices
from apps.workshops.models.workshops import Workshop


class ApplyProductImportPricesTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Preco Import",
            cnpj="11.222.333/0001-44",
            phone="+5511999999999",
            address="Rua Preco, 10",
        )
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Preco")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="PRECO-1",
            name="Produto Preco",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
        )

    def test_updates_catalog_cost_and_selling_prices(self) -> None:
        apply_product_import_prices(
            product=self.product,
            purchase_price=Money("15.00", "BRL"),
            selling_price=Money("30.00", "BRL"),
        )

        self.product.refresh_from_db()
        self.assertEqual(self.product.cost_price, Money("15.00", "BRL"))
        self.assertEqual(self.product.selling_price, Money("30.00", "BRL"))
        self.assertEqual(self.product.last_purchase_price, Money("15.00", "BRL"))
        self.assertEqual(self.product.last_used_price, Money("30.00", "BRL"))
        self.assertEqual(self.product.profit_margin, Decimal("50.00"))

    def test_recalculates_profit_margin_when_prices_change(self) -> None:
        apply_product_import_prices(
            product=self.product,
            purchase_price=Money("12.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )

        self.product.refresh_from_db()
        self.assertEqual(self.product.profit_margin, Decimal("40.00"))

    def test_does_not_clear_catalog_prices_when_import_values_are_missing(self) -> None:
        apply_product_import_prices(product=self.product, purchase_price=None, selling_price=None)

        self.product.refresh_from_db()
        self.assertEqual(self.product.cost_price, Money("10.00", "BRL"))
        self.assertEqual(self.product.selling_price, Money("20.00", "BRL"))
        self.assertIsNone(self.product.last_purchase_price)
        self.assertIsNone(self.product.last_used_price)
        self.assertEqual(self.product.profit_margin, Decimal("50.00"))
