from datetime import datetime
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils import timezone


class ProductSupplierTemplateTests(SimpleTestCase):
    def test_links_latest_purchase_and_nf_to_its_stock_import(self) -> None:
        supplier = SimpleNamespace(
            name="Fornecedor Teste",
            cnpj="12.345.678/0001-90",
            contact_person="",
            email="",
            phone="",
            mobile="",
            full_address="—",
        )
        item = SimpleNamespace(
            supplier=supplier,
            is_current=False,
            last_purchase_date=timezone.make_aware(datetime(2026, 9, 2, 10, 30)),
            last_purchase_quantity=2,
            last_unit_cost=None,
            last_total_value=None,
            last_purchase_nf="123456",
            last_purchase_import_id=42,
            purchase_history=[
                {
                    "date": timezone.make_aware(datetime(2026, 9, 2, 10, 30)),
                    "nf": "123456",
                    "quantity": 2,
                    "import_id": 42,
                },
                {
                    "date": timezone.make_aware(datetime(2026, 9, 1, 9, 50)),
                    "nf": "123455",
                    "quantity": 8,
                    "import_id": 41,
                },
            ],
        )

        html = render_to_string("products/sections/product_supplier.html", {"product_suppliers": [item]})

        self.assertIn('href="/stock/stock_update/42"', html)
        self.assertIn("123456", html)
        self.assertIn("Histórico de compras e NFs (2)", html)
        self.assertIn('href="/stock/stock_update/41"', html)
        self.assertIn("123455", html)
