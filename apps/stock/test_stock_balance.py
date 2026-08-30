from __future__ import annotations

from django.test import TestCase
from djmoney.money import Money

from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.stock.models import StockMovement, StockProduct
from apps.stock.services.stock_balance import calculate_approved_stock_balance
from apps.workshops.models.workshops import Workshop


class ApprovedStockBalanceTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Saldo",
            cnpj="11.222.333/0001-44",
            phone="+5511999999999",
            address="Rua Teste, 123",
        )
        group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Saldo")
        product = Product.objects.create(
            workshop=self.workshop,
            group=group,
            code="SALDO-001",
            name="Produto Saldo",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )
        self.stock_product = StockProduct.objects.get(workshop=self.workshop, product=product)

    def test_calculates_only_approved_entries_and_exits(self) -> None:
        StockMovement.objects.create(
            workshop=self.workshop,
            stock_product=self.stock_product,
            type=StockMovement.MovementType.ENTRY,
            quantity=5,
            status=StockMovement.MovementStatus.APPROVED,
        )
        StockMovement.objects.create(
            workshop=self.workshop,
            stock_product=self.stock_product,
            type=StockMovement.MovementType.EXIT,
            quantity=2,
            status=StockMovement.MovementStatus.APPROVED,
        )
        StockMovement.objects.create(
            workshop=self.workshop,
            stock_product=self.stock_product,
            type=StockMovement.MovementType.ENTRY,
            quantity=10,
            status=StockMovement.MovementStatus.WAITING,
        )

        self.assertEqual(calculate_approved_stock_balance(stock_product=self.stock_product), 3)
