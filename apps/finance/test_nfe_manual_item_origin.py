from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from djmoney.money import Money

from apps.accounts.models import Account
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.customer.models import Customer
from apps.finance.models import NfeEmissionOrigin, NfeManualItemOrigin, NfeRequest, NfeRequestManualItem
from apps.workshops.models.workshops import Workshop


class NfeRequestManualItemOriginTests(TestCase):
    def setUp(self) -> None:
        account = Account.objects.create(name="Conta item fiscal temporário")
        self.workshop = Workshop.objects.create(
            account=account,
            name="Oficina item fiscal temporário",
            cnpj="12.345.678/0001-92",
            phone="+5511988888877",
            address="Rua Estrutural, 100",
        )
        recipient = Customer.objects.create(
            workshop=self.workshop,
            name="Destinatário Estrutural",
            cpf_or_cnpj="52998224725",
            phone="+5511977777766",
            email="estrutural@example.com",
        )
        group = CatalogGroup.objects.create(workshop=self.workshop, name="Produtos estruturais")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=group,
            code="EST-001",
            name="Produto Estrutural",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            ncm="87089990",
            origin_cst=Product.OriginCST.NACIONAL,
        )
        self.nfe_request = NfeRequest.objects.create(
            workshop=self.workshop,
            manual_recipient=recipient,
            emission_origin=NfeEmissionOrigin.MANUAL,
            pricing_slider=0,
            tax_class="REF-MANUAL",
        )
        self.snapshot = {
            "description": "Produto somente desta NF-e",
            "code": "TEMP-001",
            "ncm": "84212300",
            "unit": "UN",
            "origin_cst": 0,
            "cest": "",
        }

    def test_catalog_item_continues_working_without_snapshot(self) -> None:
        item = NfeRequestManualItem.objects.create(
            request=self.nfe_request,
            product=self.product,
            quantity=Decimal("1.0000"),
            unit_price=Decimal("20.00"),
        )

        self.assertEqual(item.item_origin, NfeManualItemOrigin.CATALOG)
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.fiscal_snapshot, {})

    def test_temporary_item_can_be_saved_with_fiscal_snapshot(self) -> None:
        item = NfeRequestManualItem.objects.create(
            request=self.nfe_request,
            item_origin=NfeManualItemOrigin.TEMPORARY,
            product=None,
            fiscal_snapshot=self.snapshot,
            quantity=Decimal("2.0000"),
            unit_price=Decimal("35.00"),
        )

        self.assertIsNone(item.product)
        self.assertEqual(item.fiscal_snapshot["code"], "TEMP-001")

    def test_temporary_item_without_fiscal_snapshot_is_rejected(self) -> None:
        with self.assertRaisesMessage(ValidationError, "Informe os dados fiscais do produto temporário"):
            NfeRequestManualItem.objects.create(
                request=self.nfe_request,
                item_origin=NfeManualItemOrigin.TEMPORARY,
                product=None,
                quantity=Decimal("1.0000"),
                unit_price=Decimal("35.00"),
            )

    def test_temporary_item_with_incomplete_snapshot_is_rejected(self) -> None:
        incomplete_snapshot = {**self.snapshot, "ncm": ""}

        with self.assertRaisesMessage(ValidationError, "O NCM deve possuir 8 dígitos"):
            NfeRequestManualItem.objects.create(
                request=self.nfe_request,
                item_origin=NfeManualItemOrigin.TEMPORARY,
                product=None,
                fiscal_snapshot=incomplete_snapshot,
                quantity=Decimal("1.0000"),
                unit_price=Decimal("35.00"),
            )

    def test_catalog_item_without_product_is_rejected(self) -> None:
        with self.assertRaisesMessage(ValidationError, "Itens de catálogo exigem um produto cadastrado"):
            NfeRequestManualItem.objects.create(
                request=self.nfe_request,
                item_origin=NfeManualItemOrigin.CATALOG,
                product=None,
                quantity=Decimal("1.0000"),
                unit_price=Decimal("35.00"),
            )

    def test_existing_call_pattern_defaults_to_catalog_origin(self) -> None:
        item = NfeRequestManualItem(
            request=self.nfe_request,
            product=self.product,
            quantity=Decimal("1.0000"),
            unit_price=Decimal("20.00"),
        )

        item.full_clean()

        self.assertEqual(item.item_origin, NfeManualItemOrigin.CATALOG)
