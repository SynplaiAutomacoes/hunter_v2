from __future__ import annotations
from datetime import datetime
from types import SimpleNamespace
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils import timezone

class ProductMovementTemplateTests(SimpleTestCase):
    def test_renders_stock_adjustment_labels_and_empty_nf(self) -> None:
        movement = SimpleNamespace(criado_em=timezone.make_aware(datetime(2026, 7, 9)), type="ENTRADA", transcation_by=None, quantity=2, status="APROVADO", get_status_display="Aprovado", display_date=timezone.make_aware(datetime(2026, 7, 9)), workorder_reference=None, workorder_id=None, workorder=None, is_stock_adjustment=True, historical_supplier=None, stock_product=SimpleNamespace(last_nf_display="127037"))
        html = render_to_string("products/sections/product_movement.html", {"movements": [movement]})
        self.assertEqual(html.count("AJUSTE ESTOQUE"), 2)
        self.assertIn("bg-warning/10", html)
        self.assertNotIn("127037", html)
