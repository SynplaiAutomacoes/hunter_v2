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
            supplier=None,
            status="APROVADO",
            get_status_display="Aprovado",
        )

        html = render_to_string("products/sections/product_movement.html", {"movements": [movement]})

        self.assertIn("Sistema", html)
