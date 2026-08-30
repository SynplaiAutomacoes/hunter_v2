from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils import timezone


class ProductMovementTemplateTests(SimpleTestCase):
    def test_renders_system_when_movement_has_no_user(self) -> None:
        movement = SimpleNamespace(
            criado_em=timezone.make_aware(datetime(2026, 7, 9, 0, 42)),
            type="SAIDA",
            transcation_by=None,
            quantity=1,
            reason="",
            supplier=None,
            status="APROVADO",
            get_status_display="Aprovado",
            display_date=timezone.make_aware(datetime(2026, 7, 9, 0, 42)),
            workorder_reference=None,
        )

        html = render_to_string("products/sections/product_movement.html", {"movements": [movement]})

        self.assertIn("Sistema", html)
        self.assertIn("Nota de Entrada", html)
        self.assertIn("Motivo", html)
        self.assertIn("—", html)

    def test_renders_reason_when_present(self) -> None:
        movement = SimpleNamespace(
            criado_em=timezone.make_aware(datetime(2026, 7, 9, 0, 42)),
            type="ENTRADA",
            transcation_by=None,
            quantity=2,
            reason="Inventário físico",
            supplier=None,
            status="APROVADO",
            get_status_display="Aprovado",
            display_date=timezone.make_aware(datetime(2026, 7, 9, 0, 42)),
            workorder_reference=None,
        )

        html = render_to_string("products/sections/product_movement.html", {"movements": [movement]})

        self.assertIn("Inventário físico", html)

    def test_highlights_stock_adjustments(self) -> None:
        movement = SimpleNamespace(
            criado_em=timezone.make_aware(datetime(2026, 7, 9, 0, 42)),
            type="ENTRADA",
            transcation_by=None,
            quantity=2,
            reason="Inventário físico",
            supplier=None,
            status="APROVADO",
            get_status_display="Aprovado",
            display_date=timezone.make_aware(datetime(2026, 7, 9, 0, 42)),
            workorder_reference=None,
            is_stock_adjustment=True,
        )

        html = render_to_string("products/sections/product_movement.html", {"movements": [movement]})

        self.assertEqual(html.count("AJUSTE ESTOQUE"), 1)
        self.assertIn("bg-warning/10", html)
