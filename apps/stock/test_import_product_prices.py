from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from djmoney.money import Money

from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.stock.forms import ImportStepSummaryForm
from apps.stock.models import StockImport
from apps.workshops.models.workshops import Workshop


User = get_user_model()


class ImportExistingProductPriceSyncTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Import Preco",
            cnpj="22.333.444/0001-55",
            phone="+5511888888888",
            address="Rua Importacao, 20",
        )
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Import Preco")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="IMP-PRECO-1",
            name="Produto Existente",
            unit=Product.Unit.UND,
            cost_price=Money("93.60", "BRL"),
            selling_price=Money("202.78", "BRL"),
            profit_margin=Decimal("53.84"),
        )
        self.user = User.objects.create_user(username="import-price-user", password="secret", cpf="12345678909")
        self.stock_import = StockImport.objects.create(
            workshop=self.workshop,
            user=self.user,
            nf_key="1" * 44,
            nf_number="123",
            method=StockImport.ImportMethods.XML,
            items_data=[
                {
                    "linked_product_id": str(self.product.pk),
                    "ref": "IMP-PRECO-1",
                    "desc": "Produto Existente",
                    "qtd": "2",
                    "valor": "110.00",
                    "selling_price": "250.00",
                }
            ],
            payments_data=[],
        )
        self.request = RequestFactory().post("/")
        self.request.user = self.user

    def test_finalize_updates_existing_product_catalog_prices(self) -> None:
        form = ImportStepSummaryForm(
            instance=self.stock_import,
            workshop=self.workshop,
            request=self.request,
            import_items=self.stock_import.items_data,
            import_payments=[],
        )

        form.save()

        self.product.refresh_from_db()
        self.stock_import.refresh_from_db()
        self.assertEqual(self.stock_import.status, StockImport.ImportStatus.COMPLETED)
        self.assertEqual(self.product.cost_price, Money("110.00", "BRL"))
        self.assertEqual(self.product.selling_price, Money("250.00", "BRL"))
        self.assertEqual(self.product.last_purchase_price, Money("110.00", "BRL"))
        self.assertEqual(self.product.last_used_price, Money("250.00", "BRL"))
        self.assertEqual(self.product.profit_margin, Decimal("56.00"))
