from __future__ import annotations

from datetime import date

from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetStatus
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit, KitProduct
from apps.catalog.models.products import Product
from apps.core.infrastructure.kit_prefetch import workorder_items_with_kit_prefetch
from apps.finance.forms.emission import _build_step3_rows
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


class EmissionStep3PrefetchRegressionTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Emission Prefetch",
            cnpj="12.345.678/0001-90",
            phone="+5511987654321",
            address="Rua Emission, 100",
        )
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Emission")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="EM-P-1",
            name="Componente Emission",
            unit=Product.Unit.UND,
            cost_price=Money("5.00", "BRL"),
            selling_price=Money("10.00", "BRL"),
        )
        self.kit = Kit.objects.create(workshop=self.workshop, name="Kit Emission")
        KitProduct.objects.create(kit=self.kit, product=self.product, quantity=2)
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 13),
            status=BudgetStatus.APPROVED,
            current_step=6,
        )
        self.workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            status=WorkOrderStatus.APPROVED,
            budget_type="sale",
        )
        # save() freezes kit components into WorkOrderKitItemOverride via ensure_kit_snapshot()
        WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            kit=self.kit,
            description="Kit Emission",
            quantity=1,
        )

    def test_build_step3_rows_reuses_nested_kit_prefetch_without_valueerror(self) -> None:
        workorder = (
            WorkOrder.objects.select_related("budget", "budget__customer", "budget__vehicle")
            .prefetch_related(workorder_items_with_kit_prefetch(with_kit_tree=True))
            .filter(pk=self.workorder.pk, workshop=self.workshop)
            .get()
        )

        product_rows, service_rows = _build_step3_rows(workorder=workorder)

        self.assertEqual(len(product_rows), 1)
        self.assertEqual(len(service_rows), 0)
        self.assertIn("Kit:", product_rows[0]["origin"])
        self.assertEqual(product_rows[0]["quantity"], 2)
