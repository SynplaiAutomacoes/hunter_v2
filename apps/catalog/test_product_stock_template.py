from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase


class ProductStockTemplateTests(SimpleTestCase):
    def test_renders_stock_quantity_in_html_number_format(self) -> None:
        stock_obj = SimpleNamespace(
            current_quantity=Decimal("36.0000"),
            minimum_quantity=Decimal("10.0000"),
            restock_quantity=Decimal("0.0000"),
        )

        html = render_to_string("products/sections/product_stock.html", {"stock_obj": stock_obj, "product": SimpleNamespace(id=638)})

        self.assertIn('value="36.0000"', html)
        self.assertNotIn('value="36,0000"', html)
        self.assertEqual(html.count('step="any"'), 3)
