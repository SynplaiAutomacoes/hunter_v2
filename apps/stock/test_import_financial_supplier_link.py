from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.finance.models import FinancialMovement, PaymentMethod
from apps.stock.financial_entries import sync_payment_entries_with_financial_movements
from apps.stock.models import StockImport
from apps.suppliers.models import Supplier
from apps.workshops.models.workshops import Workshop


User = get_user_model()


class ImportFinancialSupplierLinkTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Vínculo Financeiro",
            cnpj="22.333.444/0001-55",
            phone="+5511888888888",
            address="Rua Teste, 10",
        )
        self.user = User.objects.create_user(
            username="import-financial-supplier-user",
            password="secret",
            cpf="12345678909",
        )
        self.payment_method = PaymentMethod.objects.create(
            workshop=self.workshop,
            description="Boleto",
            payment_type=PaymentMethod.PaymentType.DEBIT,
        )
        self.supplier = Supplier.objects.create(
            workshop=self.workshop,
            name="Fornecedor da NF",
            cnpj="04.252.011/0001-10",
        )
        self.stock_import = StockImport.objects.create(
            workshop=self.workshop,
            user=self.user,
            nf_key="1" * 44,
            nf_number="123",
            supplier_name=self.supplier.name,
            supplier_cnpj=self.supplier.cnpj,
        )

    def test_import_payment_links_canonical_supplier_and_preserves_source(self) -> None:
        entries, updated = sync_payment_entries_with_financial_movements(
            stock_import=self.stock_import,
            entries=[{"id": 1, "method": self.payment_method.pk, "total_paid": "150.00"}],
            user=self.user,
        )

        movement = FinancialMovement.objects.get(pk=entries[0]["financial_movement_id"])

        self.assertTrue(updated)
        self.assertEqual(movement.supplier_id, self.supplier.pk)
        self.assertIsNotNone(movement.source_id)
        self.assertEqual(movement.source.name, self.supplier.name)

    def test_sync_does_not_replace_supplier_selected_manually(self) -> None:
        other_supplier = Supplier.objects.create(
            workshop=self.workshop,
            name="Fornecedor Ajustado Manualmente",
            cnpj="33.000.167/0001-01",
        )
        movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            supplier=other_supplier,
            direction=FinancialMovement.MovementDirection.DEBIT,
            amount="150.00",
        )

        entries, updated = sync_payment_entries_with_financial_movements(
            stock_import=self.stock_import,
            entries=[{"id": 1, "method": self.payment_method.pk, "total_paid": "150.00", "financial_movement_id": movement.pk}],
            user=self.user,
        )

        movement.refresh_from_db()
        self.assertFalse(updated)
        self.assertEqual(entries[0]["financial_movement_id"], movement.pk)
        self.assertEqual(movement.supplier_id, other_supplier.pk)
