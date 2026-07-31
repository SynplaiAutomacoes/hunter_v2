from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from apps.budget.approval import approve_budget_with_stock
from apps.budget.models import Budget, BudgetItem, BudgetStatus
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.stock.models import StockMovement
from apps.workshops.models.workshops import Workshop


User = get_user_model()


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Budget {suffix}",
        cnpj=f"81.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Budget, 123",
        uf="SP",
    )


def create_product(*, workshop: Workshop, suffix: int) -> Product:
    group = CatalogGroup.objects.create(workshop=workshop, name=f"Grupo Budget {suffix}")
    return Product.objects.create(
        workshop=workshop,
        group=group,
        code=f"BUD-{suffix}",
        name=f"Produto Budget {suffix}",
        unit=Product.Unit.UND,
        cost_price=Money("40.00", "BRL"),
        selling_price=Money("80.00", "BRL"),
        ncm="12345678",
    )


class BudgetApprovalTests(TestCase):
    def test_approve_budget_does_not_change_inventory(self) -> None:
        workshop = create_workshop(suffix=1)
        user = User.objects.create_user(username="budget", password="senha123", cpf="12345678902")
        product = create_product(workshop=workshop, suffix=1)
        stock_product = product.stock_products
        stock_product.current_quantity = 10
        stock_product.save(update_fields=["current_quantity"])
        budget = Budget.objects.create(
            workshop=workshop,
            entry_date=date(2026, 7, 8),
            status=BudgetStatus.DRAFT,
            current_step=6,
            service_expected_completion_at=timezone.now(),
            customer_agreed_departure_at=timezone.now() + timedelta(days=1),
        )
        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            product=product,
            quantity=4,
        )

        with patch("apps.finance.services.workorder_financial_movements.sync_workorder_financial_movement"):
            approve_budget_with_stock(budget=budget, user=user)

        budget.refresh_from_db()
        stock_product.refresh_from_db()

        self.assertEqual(budget.status, BudgetStatus.APPROVED)
        self.assertEqual(stock_product.current_quantity, 10)
        self.assertFalse(StockMovement.objects.exists())
        self.assertEqual(budget.workorders.count(), 1)
        self.assertEqual(budget.workorders.get().items.count(), 1)
