from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetStatus
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.workorder_financial_movements import workorder_payment_has_paid_movements
from apps.workorder.models import WorkOrder, WorkOrderPaymentMethod, WorkOrderStatus
from apps.workorder.reopening import reopen_workorder
from apps.workorder.util import PAID_PAYMENT_DELETE_MESSAGE
from apps.workorder.views import DeletePaymentMethodView
from apps.workshops.models.workshops import Workshop


User = get_user_model()


def _create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Pagamento Pago {suffix}",
        cnpj=f"55.666.777/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Pagamento, 1",
        uf="SP",
    )


class WorkorderPaymentPaidGuardTests(TestCase):
    def setUp(self) -> None:
        self.workshop = _create_workshop(suffix=1)
        self.user = User.objects.create_user(username="paid-guard-user", password="senha123", cpf="12345678904")
        self.payment_method = PaymentMethod.objects.create(
            workshop=self.workshop,
            description="Cartão",
            tax_percentage=Decimal("2.00"),
        )
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 8, 1),
            status=BudgetStatus.APPROVED,
            current_step=6,
        )
        self.workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            status=WorkOrderStatus.APPROVED,
            budget_type="sale",
        )
        self.payment = WorkOrderPaymentMethod.objects.create(
            workorder=self.workorder,
            payment_method=self.payment_method,
            installments_count=1,
            first_installment_amount=Money("500.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            due_date=date(2026, 8, 15),
        )

    def _create_parent_movement(self, *, is_paid: bool) -> FinancialMovement:
        return FinancialMovement.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            workorder_payment=self.payment,
            direction=FinancialMovement.MovementDirection.CREDIT,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            description="Receita proveniente de ordem de serviço",
            amount=Money("500.00", "BRL"),
            due_date=date(2026, 8, 15),
            payment_method=self.payment_method,
            is_paid=is_paid,
        )

    def _create_card_fee_movement(self, *, is_paid: bool) -> FinancialMovement:
        return FinancialMovement.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            workorder_payment=self.payment,
            direction=FinancialMovement.MovementDirection.DEBIT,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
            description="Pagamento da taxa da maquininha",
            amount=Money("10.00", "BRL"),
            due_date=date(2026, 8, 15),
            payment_method=self.payment_method,
            is_paid=is_paid,
        )

    def test_reopen_preserves_financial_movements(self) -> None:
        movement = self._create_parent_movement(is_paid=True)

        reopen_workorder(workorder=self.workorder, user=self.user, reason="Corrigir pagamento")

        movement.refresh_from_db()
        self.assertTrue(FinancialMovement.objects.filter(pk=movement.pk, is_paid=True).exists())

    def test_delete_unpaid_payment_removes_movement(self) -> None:
        movement = self._create_parent_movement(is_paid=False)
        payment_pk = self.payment.pk

        view = DeletePaymentMethodView()
        view.workshop = self.workshop
        request = RequestFactory().delete(f"/workorder/delete_payment/{payment_pk}/")
        request.user = self.user

        response = view.delete(request, pk=payment_pk)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(WorkOrderPaymentMethod.objects.filter(pk=payment_pk).exists())
        self.assertFalse(FinancialMovement.objects.filter(pk=movement.pk).exists())

    def test_delete_paid_payment_returns_409(self) -> None:
        self._create_parent_movement(is_paid=True)

        view = DeletePaymentMethodView()
        view.workshop = self.workshop
        request = RequestFactory().delete(f"/workorder/delete_payment/{self.payment.pk}/")
        request.user = self.user

        response = view.delete(request, pk=self.payment.pk)

        self.assertEqual(response.status_code, 409)
        payload = json.loads(response.content)
        self.assertEqual(payload["error"], PAID_PAYMENT_DELETE_MESSAGE)
        self.assertIn("showPaymentPaidLockModal", json.loads(response["HX-Trigger"]))
        self.assertTrue(WorkOrderPaymentMethod.objects.filter(pk=self.payment.pk).exists())

    def test_delete_blocked_when_card_fee_paid(self) -> None:
        self._create_parent_movement(is_paid=False)
        self._create_card_fee_movement(is_paid=True)

        self.assertTrue(workorder_payment_has_paid_movements(payment=self.payment))

        view = DeletePaymentMethodView()
        view.workshop = self.workshop
        request = RequestFactory().delete(f"/workorder/delete_payment/{self.payment.pk}/")
        request.user = self.user

        response = view.delete(request, pk=self.payment.pk)

        self.assertEqual(response.status_code, 409)
        self.assertTrue(WorkOrderPaymentMethod.objects.filter(pk=self.payment.pk).exists())
