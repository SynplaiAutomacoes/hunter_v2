from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from djmoney.money import Money

from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.stock.financial_entries import sync_payment_entries_with_financial_movements
from apps.stock.models import StockImport
from apps.workshops.models.workshops import Workshop


User = get_user_model()


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Estoque {suffix}",
        cnpj=f"191312430001{suffix:02d}",
        phone="+5511999999999",
        address="Rua Estoque, 123",
        uf="SP",
    )


class StockImportFinancialEntrySyncTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=1)
        self.user = User.objects.create_user(username="estoque", password="senha123", cpf="12345678901")
        self.payment_method = PaymentMethod.objects.create(
            workshop=self.workshop,
            description="BOLETO",
            payment_type=PaymentMethod.PaymentType.BOTH,
            is_active=True,
        )

    def test_sync_creates_financial_movements_for_automatic_import_payments(self) -> None:
        stock_import = StockImport.objects.create(
            workshop=self.workshop,
            user=self.user,
            nf_number="12345",
            nf_key="1" * 44,
            supplier_name="Fornecedor Teste",
            supplier_cnpj="12345678000195",
            payments_data=[],
        )

        synced_entries, updated = sync_payment_entries_with_financial_movements(
            stock_import=stock_import,
            entries=[
                {
                    "id": 1,
                    "method": self.payment_method.pk,
                    "method_display": "BOLETO",
                    "installments": 1,
                    "first_amount": "1000.00",
                    "total_paid": "1000.00",
                    "payment_date": "2026-07-07",
                }
            ],
            user=self.user,
            replace_existing=True,
        )

        self.assertTrue(updated)
        self.assertIn("financial_movement_id", synced_entries[0])

        movement = FinancialMovement.objects.get(pk=synced_entries[0]["financial_movement_id"])
        self.assertEqual(movement.workshop, self.workshop)
        self.assertEqual(movement.user, self.user)
        self.assertEqual(movement.payment_method, self.payment_method)
        self.assertEqual(movement.direction, FinancialMovement.MovementDirection.DEBIT)
        self.assertEqual(movement.due_date, date(2026, 7, 7))
        self.assertEqual(str(movement.amount.amount), "1000.00")
        self.assertEqual(movement.description, "Pagamento Importação de Estoque - NF: 12345")

    def test_sync_removes_stale_financial_movements_when_replacing_imported_payments(self) -> None:
        old_movement = FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Pagamento Importação de Estoque - NF: 12345",
            payment_method=self.payment_method,
            nf_number="12345",
            amount=Money("500.00", "BRL"),
            due_date=date(2026, 7, 7),
            is_paid=False,
        )
        stock_import = StockImport.objects.create(
            workshop=self.workshop,
            user=self.user,
            nf_number="12345",
            nf_key="2" * 44,
            supplier_name="Fornecedor Teste",
            supplier_cnpj="12345678000195",
            payments_data=[
                {
                    "id": 1,
                    "method": self.payment_method.pk,
                    "total_paid": "500.00",
                    "payment_date": "2026-07-07",
                    "financial_movement_id": old_movement.pk,
                }
            ],
        )

        synced_entries, updated = sync_payment_entries_with_financial_movements(
            stock_import=stock_import,
            entries=[
                {
                    "id": 1,
                    "method": self.payment_method.pk,
                    "total_paid": "800.00",
                    "payment_date": "2026-08-07",
                }
            ],
            user=self.user,
            replace_existing=True,
        )

        self.assertTrue(updated)
        self.assertFalse(FinancialMovement.objects.filter(pk=old_movement.pk).exists())

        new_movement = FinancialMovement.objects.get(pk=synced_entries[0]["financial_movement_id"])
        self.assertEqual(new_movement.due_date, date(2026, 8, 7))
        self.assertEqual(str(new_movement.amount.amount), "800.00")
