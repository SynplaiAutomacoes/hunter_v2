from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.workorder.models import WorkOrder, WorkOrderItem
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina OS {suffix}",
        cnpj=f"11.333.444/0001-{suffix:02d}",
        phone="+5511988888888",
        address="Rua Teste OS, 123",
    )


def create_budget(*, workshop: Workshop) -> Budget:
    budget = Budget(workshop=workshop, entry_date=timezone.now().date())
    budget.save()
    return budget


class WorkOrderTotalsConsistencyTests(TestCase):
    def test_total_base_value_uses_workorder_item_selling_totals_only(self) -> None:
        workshop = create_workshop(suffix=81)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        group = CatalogGroup.objects.create(workshop=workshop, name="Grupo Teste")
        product = Product.objects.create(
            workshop=workshop,
            code="P-001",
            unit=Product.Unit.UND,
            name="Produto Teste",
            group=group,
            cost_price=Money("50.00", "BRL"),
            selling_price=Money("100.00", "BRL"),
        )
        service = Service.objects.create(
            workshop=workshop,
            name="Servico Teste",
            duration=timedelta(hours=1),
            suggested_cost=Money("0.00", "BRL"),
            selling_price=Money("0.01", "BRL"),
        )

        WorkOrderItem.objects.create(
            workshop=workshop,
            workorder=workorder,
            product=product,
            quantity=2,
            shipping=Money("5.00", "BRL"),
        )
        WorkOrderItem.objects.create(
            workshop=workshop,
            workorder=workorder,
            service=service,
            quantity=1,
        )

        with patch.object(WorkOrder, "calculate_pricing_methods", side_effect=AssertionError("Nao deve usar metodo de precificacao para total_base_value")):
            self.assertEqual(workorder.total_products_value, Money("205.00", "BRL"))
            self.assertEqual(workorder.total_services_value, Money("0.01", "BRL"))
            self.assertEqual(workorder.total_base_value, Money("205.01", "BRL"))

    def test_total_budget_value_applies_discount_over_item_totals(self) -> None:
        workshop = create_workshop(suffix=82)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        group = CatalogGroup.objects.create(workshop=workshop, name="Grupo Desconto")
        product = Product.objects.create(
            workshop=workshop,
            code="P-002",
            unit=Product.Unit.UND,
            name="Produto Desconto",
            group=group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("15.00", "BRL"),
        )
        WorkOrderItem.objects.create(
            workshop=workshop,
            workorder=workorder,
            product=product,
            quantity=1,
        )

        workorder.discount_value = Money(Decimal("5.00"), "BRL")
        workorder.save(update_fields=["discount_value"])

        self.assertEqual(workorder.total_base_value, Money("15.00", "BRL"))
        self.assertEqual(workorder.total_budget_value, Money("10.00", "BRL"))
