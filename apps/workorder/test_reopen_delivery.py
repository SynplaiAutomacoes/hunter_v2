from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetStatus
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.stock.models import StockMovement
from apps.stock.services.workorder_stock import get_reversed_stock_movement_ids, has_unreversed_exit_movements
from apps.workorder.approval import approve_workorder_with_stock
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderStatus
from apps.workorder.reopening import reopen_workorder
from apps.workshops.models.workshops import Workshop


User = get_user_model()


def _count_unreversed_exits(*, workorder: WorkOrder) -> int:
    return (
        StockMovement.objects.filter(
            workorder=workorder,
            type=StockMovement.MovementType.EXIT,
        )
        .exclude(pk__in=get_reversed_stock_movement_ids())
        .count()
    )


class ReopenDeliveryTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Reabertura",
            cnpj="12.345.678/0001-91",
            phone="+5511999999999",
            address="Rua Reabertura, 1",
            uf="SP",
        )
        self.user = User.objects.create_user(username="reopen-user", password="senha123", cpf="12345678903")
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Reabertura")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="REO-1",
            name="Produto Reabertura",
            unit=Product.Unit.UND,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            ncm="12345678",
        )
        self.stock_product = self.product.stock_products
        self.stock_product.current_quantity = 20
        self.stock_product.save(update_fields=["current_quantity"])
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 21),
            status=BudgetStatus.APPROVED,
            current_step=6,
        )
        self.workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            status=WorkOrderStatus.DRAFT,
            budget_type="sale",
        )
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            product=self.product,
            quantity=2,
        )

    def test_reopened_workorder_with_products_can_be_delivered_again(self) -> None:
        approve_workorder_with_stock(workorder=self.workorder, user=self.user)
        self.workorder.refresh_from_db()
        self.assertEqual(self.workorder.status, WorkOrderStatus.APPROVED)
        self.assertEqual(_count_unreversed_exits(workorder=self.workorder), 1)
        self.assertEqual(
            StockMovement.objects.filter(workorder=self.workorder, type=StockMovement.MovementType.EXIT).latest("pk").reason,
            "Fechamento de O.S.",
        )

        reopen_workorder(workorder=self.workorder, user=self.user, reason="Corrigir item da O.S.")
        self.workorder.refresh_from_db()
        self.assertEqual(self.workorder.status, WorkOrderStatus.WAITING_DELIVERY)
        self.assertFalse(has_unreversed_exit_movements(workorder=self.workorder))
        self.assertEqual(
            StockMovement.objects.filter(workorder=self.workorder, type=StockMovement.MovementType.ENTRY).latest("pk").reason,
            "Reabertura de O.S.",
        )

        approve_workorder_with_stock(workorder=self.workorder, user=self.user)
        self.workorder.refresh_from_db()
        self.assertEqual(self.workorder.status, WorkOrderStatus.APPROVED)
        self.assertEqual(_count_unreversed_exits(workorder=self.workorder), 1)

    def test_reopened_service_only_workorder_can_be_delivered_again(self) -> None:
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço Reabertura",
            duration=timedelta(hours=1),
            suggested_cost=Money("50.00", "BRL"),
            selling_price=Money("100.00", "BRL"),
        )
        service_budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 21),
            status=BudgetStatus.APPROVED,
            current_step=6,
        )
        service_workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=service_budget,
            status=WorkOrderStatus.DRAFT,
            budget_type="sale",
        )
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=service_workorder,
            service=service,
            quantity=1,
            duration=timedelta(hours=1),
            service_cost_price=Money("50.00", "BRL"),
            service_selling_price=Money("100.00", "BRL"),
        )

        approve_workorder_with_stock(workorder=service_workorder, user=self.user)
        service_workorder.refresh_from_db()
        self.assertEqual(service_workorder.status, WorkOrderStatus.APPROVED)

        reopen_workorder(workorder=service_workorder, user=self.user, reason="Ajustar serviço")
        service_workorder.refresh_from_db()
        self.assertEqual(service_workorder.status, WorkOrderStatus.WAITING_DELIVERY)

        approve_workorder_with_stock(workorder=service_workorder, user=self.user)
        service_workorder.refresh_from_db()
        self.assertEqual(service_workorder.status, WorkOrderStatus.APPROVED)
