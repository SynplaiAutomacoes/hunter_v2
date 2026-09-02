from datetime import datetime
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils import timezone


class ProductMovementTemplateTests(SimpleTestCase):
    def test_renders_stock_adjustment_labels_and_empty_nf(self) -> None:
        movement = SimpleNamespace(
            criado_em=timezone.make_aware(datetime(2026, 7, 9)),
            type="ENTRADA",
            transcation_by=None,
            quantity=2,
            status="APROVADO",
            get_status_display="Aprovado",
            display_date=timezone.make_aware(datetime(2026, 7, 9)),
            workorder_reference=None,
            workorder_id=None,
            workorder=None,
            is_stock_adjustment=True,
            reason_display="Ajuste de Estoque: Inventário físico",
            historical_supplier=None,
            stock_product=SimpleNamespace(last_nf_display="127037"),
        )

        html = render_to_string("products/sections/product_movement.html", {"movements": [movement]})

        self.assertEqual(html.count("AJUSTE ESTOQUE"), 2)
        self.assertIn("Ajuste de Estoque: Inventário físico", html)
        self.assertIn("bg-warning/10", html)
        self.assertNotIn("127037", html)

    def test_renders_system_when_movement_has_no_user(self) -> None:
        movement = SimpleNamespace(
            criado_em=timezone.make_aware(datetime(2026, 7, 9, 0, 42)),
            type="SAIDA",
            transcation_by=None,
            quantity=1,
            reason_display="Fechamento de O.S.",
            supplier=None,
            historical_supplier=None,
            workorder=None,
            workorder_id=None,
            status="APROVADO",
            get_status_display="Aprovado",
            display_date=timezone.make_aware(datetime(2026, 7, 9, 0, 42)),
            workorder_reference=None,
            is_stock_adjustment=False,
            stock_product=SimpleNamespace(last_nf_display=None),
        )

        html = render_to_string("products/sections/product_movement.html", {"movements": [movement]})

        self.assertIn("Sistema", html)
        self.assertIn("Motivo", html)
        self.assertIn("Fechamento de O.S.", html)
        self.assertIn("Fornecedor", html)
        self.assertIn("Cliente/Veículo", html)
        self.assertIn("—", html)

    def test_renders_supplier_when_present(self) -> None:
        movement = SimpleNamespace(
            criado_em=timezone.make_aware(datetime(2026, 7, 9, 0, 42)),
            type="ENTRADA",
            transcation_by=None,
            quantity=2,
            reason_display="Importação de NF 127037",
            supplier=None,
            historical_supplier=SimpleNamespace(name="Fornecedor Teste"),
            workorder=None,
            workorder_id=None,
            status="APROVADO",
            get_status_display="Aprovado",
            display_date=timezone.make_aware(datetime(2026, 7, 9, 0, 42)),
            workorder_reference=None,
            is_stock_adjustment=False,
            stock_product=SimpleNamespace(last_nf_display=None),
        )

        html = render_to_string("products/sections/product_movement.html", {"movements": [movement]})

        self.assertIn("Importação de NF 127037", html)
        self.assertIn("Fornecedor", html)
        self.assertIn("Fornecedor Teste", html)
