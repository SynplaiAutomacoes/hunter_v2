from __future__ import annotations

from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase


class StockApprovalsTemplateTests(SimpleTestCase):
    def test_renders_system_when_pending_movement_has_no_user(self) -> None:
        movement = SimpleNamespace(
            stock_product=SimpleNamespace(product=SimpleNamespace(code="P-001", name="Produto Teste")),
            type="SAIDA",
            quantity=1,
            transcation_by=None,
            pk=1,
            get_type_display="Saida",
        )

        html = render_to_string("stock/approvals.html", {"pending_movements": [movement]})

        self.assertIn("Sistema", html)
