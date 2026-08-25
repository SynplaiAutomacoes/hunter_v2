from __future__ import annotations

from datetime import date

from django import forms
from django.contrib.auth import get_user_model
from django.http import QueryDict
from django.test import RequestFactory, TestCase
from djmoney.money import Money

from apps.collaborators.test_commissions import create_financial_group_path
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.stock.financial_entries import MISSING_BUDGET_PLAN_MESSAGE, sync_payment_entries_if_budget_plans_ready, sync_payment_entries_with_financial_movements
from apps.stock.forms import ImportStepPaymentForm, ImportStepSummaryForm
from apps.stock.models import StockImport
from apps.stock.views import AddPaymentSessionView
from apps.workshops.models.workshops import Workshop


User = get_user_model()


class StockImportPaymentBudgetPlanTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Import Plano",
            cnpj="88.999.000/0001-11",
            phone="+5511999999999",
            address="Rua Importacao, 10",
        )
        self.user = User.objects.create_user(username="import-plan-user", password="secret", cpf="12345678901")
        self.payment_method = PaymentMethod.objects.create(
            workshop=self.workshop,
            description="Pix Importacao",
            payment_type=PaymentMethod.PaymentType.BOTH,
            is_active=True,
        )
        self.budget_plan = create_financial_group_path(workshop=self.workshop, code_segments=[1], names=["Despesas"])
        self.stock_import = StockImport.objects.create(
            workshop=self.workshop,
            user=self.user,
            nf_key="2" * 44,
            nf_number="456",
            method=StockImport.ImportMethods.XML,
            items_data=[{"valor": "100.00", "qtd": "1"}],
            payments_data=[],
        )

    def _post_payment(self, *, extra_data: dict[str, str] | None = None) -> object:
        data = {
            "payment_method": str(self.payment_method.pk),
            "payment_date": "2026-08-21",
            "first_amount_0": "100.00",
            "first_amount_1": "BRL",
        }
        if extra_data:
            data.update(extra_data)
        request = RequestFactory().post(f"/stock/add_payment_session/?pk={self.stock_import.pk}", data)
        request.user = self.user
        view = AddPaymentSessionView()
        view.request = request
        view.workshop = self.workshop
        return view.post(request)

    def test_add_payment_without_budget_plan_does_not_create_movement(self) -> None:
        response = self._post_payment()

        self.assertEqual(response.status_code, 204)
        self.assertEqual(FinancialMovement.objects.filter(workshop=self.workshop).count(), 0)
        self.stock_import.refresh_from_db()
        self.assertEqual(self.stock_import.payments_data, [])

    def test_add_payment_with_budget_plan_persists_on_movement(self) -> None:
        response = self._post_payment(extra_data={"budget_plan": str(self.budget_plan.pk)})

        self.assertEqual(response.status_code, 204)
        movement = FinancialMovement.objects.get(workshop=self.workshop, description__startswith="Pagamento Importação")
        self.assertEqual(movement.budget_plan_id, self.budget_plan.pk)
        self.stock_import.refresh_from_db()
        self.assertEqual(self.stock_import.payments_data[0]["budget_plan_id"], self.budget_plan.pk)

    def test_sync_payment_entries_requires_budget_plan(self) -> None:
        entries = [
            {
                "id": 1,
                "entry_type": "payment",
                "method": self.payment_method.pk,
                "total_paid": "80.00",
                "payment_date": date(2026, 8, 21),
            }
        ]

        with self.assertRaises(forms.ValidationError) as raised:
            sync_payment_entries_with_financial_movements(stock_import=self.stock_import, entries=entries, user=self.user)

        self.assertIn(MISSING_BUDGET_PLAN_MESSAGE, raised.exception.messages)
        self.assertEqual(FinancialMovement.objects.filter(workshop=self.workshop).count(), 0)

    def test_xml_payments_without_budget_plan_do_not_create_movements(self) -> None:
        entries = [
            {
                "id": 1,
                "entry_type": "payment",
                "method": self.payment_method.pk,
                "installments": 1,
                "first_amount": "100.00",
                "total_paid": "100.00",
                "payment_date": "2026-08-21",
            }
        ]

        synced, updated = sync_payment_entries_if_budget_plans_ready(
            stock_import=self.stock_import,
            entries=entries,
            user=self.user,
            replace_existing=True,
        )

        self.assertFalse(updated)
        self.assertIsNone(synced[0].get("financial_movement_id"))
        self.assertEqual(FinancialMovement.objects.filter(workshop=self.workshop).count(), 0)

    def test_payment_step_applies_budget_plan_to_xml_parcels(self) -> None:
        xml_payment = {
            "id": 1,
            "entry_type": "payment",
            "method": self.payment_method.pk,
            "method_display": self.payment_method.description,
            "installments": 1,
            "first_amount": "100.00",
            "total_paid": "100.00",
            "payment_date": "2026-08-21",
        }
        self.stock_import.payments_data = [xml_payment]
        self.stock_import.save(update_fields=["payments_data"])

        data = QueryDict(mutable=True)
        data["budget_plan"] = str(self.budget_plan.pk)
        form = ImportStepPaymentForm(
            data,
            instance=self.stock_import,
            workshop=self.workshop,
            import_items=self.stock_import.items_data,
            import_payments=self.stock_import.payments_data,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.stock_import.refresh_from_db()
        self.assertEqual(self.stock_import.payments_data[0]["budget_plan_id"], self.budget_plan.pk)

        synced, updated = sync_payment_entries_with_financial_movements(
            stock_import=self.stock_import,
            entries=list(self.stock_import.payments_data),
            user=self.user,
        )
        self.assertTrue(updated)
        movement = FinancialMovement.objects.get(pk=synced[0]["financial_movement_id"])
        self.assertEqual(movement.budget_plan_id, self.budget_plan.pk)

    def test_payment_step_requires_budget_plan_for_xml_parcels(self) -> None:
        xml_payment = {
            "id": 1,
            "entry_type": "payment",
            "method": self.payment_method.pk,
            "method_display": self.payment_method.description,
            "total_paid": "100.00",
            "payment_date": "2026-08-21",
        }
        form = ImportStepPaymentForm(
            QueryDict(mutable=True),
            instance=self.stock_import,
            workshop=self.workshop,
            import_items=self.stock_import.items_data,
            import_payments=[xml_payment],
        )

        self.assertFalse(form.is_valid())
        self.assertIn("budget_plan", form.errors)

    def test_summary_rejects_payments_without_budget_plan(self) -> None:
        self.stock_import.items_data = [{"valor": "100.00", "qtd": "1", "linked_product_id": 1, "desc": "Item"}]
        self.stock_import.payments_data = [
            {
                "id": 1,
                "entry_type": "payment",
                "method": self.payment_method.pk,
                "method_display": self.payment_method.description,
                "total_paid": "100.00",
                "payment_date": "2026-08-21",
            }
        ]
        self.stock_import.save(update_fields=["items_data", "payments_data"])

        form = ImportStepSummaryForm(
            {},
            instance=self.stock_import,
            workshop=self.workshop,
            import_items=self.stock_import.items_data,
            import_payments=self.stock_import.payments_data,
        )

        self.assertFalse(form.is_valid())
        self.assertIn(MISSING_BUDGET_PLAN_MESSAGE, form.non_field_errors())

    def test_sync_payment_entries_persists_budget_plan(self) -> None:
        entries = [
            {
                "id": 1,
                "entry_type": "payment",
                "method": self.payment_method.pk,
                "budget_plan_id": self.budget_plan.pk,
                "total_paid": "80.00",
                "payment_date": date(2026, 8, 21),
            }
        ]

        synced, updated = sync_payment_entries_with_financial_movements(
            stock_import=self.stock_import,
            entries=entries,
            user=self.user,
        )

        self.assertTrue(updated)
        movement = FinancialMovement.objects.get(pk=synced[0]["financial_movement_id"])
        self.assertEqual(movement.budget_plan_id, self.budget_plan.pk)
        self.assertEqual(movement.amount, Money("80.00", "BRL"))
