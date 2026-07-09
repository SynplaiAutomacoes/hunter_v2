from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetStatus
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.core.infrastructure.services.supersign import process_supersign_webhook_payload
from apps.stock.models import StockMovement
from apps.workorder.approval import approve_workorder_with_stock
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderPaymentMethod, WorkOrderSignatureStatus, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


User = get_user_model()


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina OS {suffix}",
        cnpj=f"91.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua OS, 123",
        uf="SP",
    )


def create_budget(*, workshop: Workshop, suffix: int, budget_type: str = "sale") -> Budget:
    return Budget.objects.create(
        workshop=workshop,
        entry_date=date(2026, 7, 8),
        status=BudgetStatus.DRAFT,
        budget_type=budget_type,
        current_step=6,
    )


def create_product(*, workshop: Workshop, suffix: int) -> Product:
    group = CatalogGroup.objects.create(workshop=workshop, name=f"Grupo OS {suffix}")
    return Product.objects.create(
        workshop=workshop,
        group=group,
        code=f"PROD-{suffix}",
        name=f"Produto OS {suffix}",
        unit=Product.Unit.UND,
        cost_price=Money("50.00", "BRL"),
        selling_price=Money("100.00", "BRL"),
        ncm="12345678",
    )


def create_workorder_with_product(*, workshop: Workshop, suffix: int, budget_type: str = "sale", quantity: int = 3, stock_quantity: int = 10, fully_paid: bool = False) -> tuple[WorkOrder, Product]:
    budget = create_budget(workshop=workshop, suffix=suffix, budget_type=budget_type)
    workorder = WorkOrder.objects.create(
        workshop=workshop,
        budget=budget,
        status=WorkOrderStatus.DRAFT,
        budget_type=budget_type,
        signature_external_id=f"envelope-{suffix}",
        signature_request_status=WorkOrderSignatureStatus.SENT,
    )
    product = create_product(workshop=workshop, suffix=suffix)
    stock_product = product.stock_products
    stock_product.current_quantity = stock_quantity
    stock_product.save(update_fields=["current_quantity"])
    WorkOrderItem.objects.create(
        workshop=workshop,
        workorder=workorder,
        product=product,
        quantity=quantity,
    )
    if fully_paid:
        WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            first_installment_amount=Money(str(quantity * 100), "BRL"),
        )
    return workorder, product


class WorkOrderApprovalTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=1)
        self.user = User.objects.create_user(username="workorder", password="senha123", cpf="12345678901")

    def test_approve_workorder_with_stock_decrements_inventory_and_creates_history(self) -> None:
        workorder, product = create_workorder_with_product(workshop=self.workshop, suffix=1)

        approve_workorder_with_stock(workorder=workorder, user=self.user)

        workorder.refresh_from_db()
        product.stock_products.refresh_from_db()
        movement = StockMovement.objects.get(workorder=workorder)

        self.assertEqual(workorder.status, WorkOrderStatus.APPROVED)
        self.assertIsNotNone(workorder.delivered_at)
        self.assertEqual(product.stock_products.current_quantity, 7)
        self.assertEqual(movement.type, StockMovement.MovementType.EXIT)
        self.assertEqual(movement.quantity, 3)
        self.assertEqual(movement.status, StockMovement.MovementStatus.APPROVED)
        self.assertEqual(movement.transcation_by, self.user)

    def test_supersign_webhook_reuses_central_stock_approval_flow(self) -> None:
        workorder, product = create_workorder_with_product(workshop=self.workshop, suffix=2, budget_type="sale", fully_paid=True)

        with patch("apps.core.infrastructure.services.supersign.sync_workorder_financial_movement") as sync_financial_movement:
            response = process_supersign_webhook_payload(payload={"event": "ENVELOPE_COMPLETED", "envelopeId": workorder.signature_external_id})

        workorder.refresh_from_db()
        product.stock_products.refresh_from_db()
        movement = StockMovement.objects.get(workorder=workorder)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(workorder.status, WorkOrderStatus.APPROVED)
        self.assertEqual(workorder.signature_request_status, WorkOrderSignatureStatus.APPROVED)
        self.assertEqual(product.stock_products.current_quantity, 7)
        self.assertEqual(movement.quantity, 3)
        sync_financial_movement.assert_called_once_with(workorder=workorder)

    def test_supersign_webhook_decrements_stock_for_courtesy_workorder(self) -> None:
        workorder, product = create_workorder_with_product(workshop=self.workshop, suffix=4, budget_type="courtesy")

        with patch("apps.core.infrastructure.services.supersign.sync_workorder_financial_movement") as sync_financial_movement:
            response = process_supersign_webhook_payload(payload={"event": "ENVELOPE_COMPLETED", "envelopeId": workorder.signature_external_id})

        workorder.refresh_from_db()
        product.stock_products.refresh_from_db()
        movement = StockMovement.objects.get(workorder=workorder)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(workorder.status, WorkOrderStatus.APPROVED)
        self.assertEqual(workorder.signature_request_status, WorkOrderSignatureStatus.APPROVED)
        self.assertEqual(product.stock_products.current_quantity, 7)
        self.assertEqual(movement.quantity, 3)
        sync_financial_movement.assert_called_once_with(workorder=workorder)

    def test_supersign_webhook_decrements_stock_for_warranty_workorder(self) -> None:
        workorder, product = create_workorder_with_product(workshop=self.workshop, suffix=5, budget_type="warranty")

        with patch("apps.core.infrastructure.services.supersign.sync_workorder_financial_movement") as sync_financial_movement:
            response = process_supersign_webhook_payload(payload={"event": "ENVELOPE_COMPLETED", "envelopeId": workorder.signature_external_id})

        workorder.refresh_from_db()
        product.stock_products.refresh_from_db()
        movement = StockMovement.objects.get(workorder=workorder)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(workorder.status, WorkOrderStatus.APPROVED)
        self.assertEqual(workorder.signature_request_status, WorkOrderSignatureStatus.APPROVED)
        self.assertEqual(product.stock_products.current_quantity, 7)
        self.assertEqual(movement.quantity, 3)
        sync_financial_movement.assert_called_once_with(workorder=workorder)

    def test_supersign_webhook_keeps_unpaid_sale_workorder_without_stock_change(self) -> None:
        workorder, product = create_workorder_with_product(workshop=self.workshop, suffix=3, budget_type="sale")

        with patch("apps.core.infrastructure.services.supersign.sync_workorder_financial_movement") as sync_financial_movement:
            response = process_supersign_webhook_payload(payload={"event": "ENVELOPE_COMPLETED", "envelopeId": workorder.signature_external_id})

        workorder.refresh_from_db()
        product.stock_products.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(workorder.status, WorkOrderStatus.DRAFT)
        self.assertEqual(workorder.signature_request_status, WorkOrderSignatureStatus.APPROVED)
        self.assertEqual(product.stock_products.current_quantity, 10)
        self.assertFalse(StockMovement.objects.filter(workorder=workorder).exists())
        sync_financial_movement.assert_not_called()
