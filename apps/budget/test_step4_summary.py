from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem, BudgetKitItemOverride, BudgetStatus, BudgetType
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.workshops.models.workshops import Workshop


def _money(amount: str) -> Money:
    return Money(amount, "BRL")


def _create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Step4 {suffix}",
        cnpj=f"22.333.444/0001-{suffix:02d}",
        phone="+5511999999999",
        address=f"Rua Step4, {suffix}",
        uf="SP",
    )


class Step4WinnerSummaryTests(TestCase):
    def setUp(self) -> None:
        self.workshop = _create_workshop(suffix=1)
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Step4")
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 8, 19),
            budget_type=BudgetType.SALE,
            status=BudgetStatus.DRAFT,
            current_step=4,
            slider=0,
        )
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="STEP4-CORREIA",
            name="Correia auxiliar T270",
            cost_price=_money("10.00"),
            selling_price=_money("154.98"),
        )
        self.clamp = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="STEP4-ABRACADEIRA",
            name="Abracadeira 12 x 44",
            cost_price=_money("2.40"),
            selling_price=_money("2.40"),
        )

    def _add_kit_with_product(self, *, kit_name: str, product: Product, quantity: int, selling: str) -> BudgetItem:
        kit = Kit.objects.create(workshop=self.workshop, name=kit_name)
        item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            kit=kit,
            quantity=1,
        )
        BudgetKitItemOverride.objects.create(
            workshop=self.workshop,
            budget_item=item,
            product=product,
            quantity=quantity,
            product_cost_price=product.cost_price,
            product_selling_price=_money(selling),
        )
        return item

    def test_step4_summary_uses_winner_instead_of_summing_overlapping_skus(self) -> None:
        self._add_kit_with_product(kit_name="Correia auxiliar kit", product=self.product, quantity=1, selling="154.98")
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=self.product,
            quantity=2,
            product_cost_price=_money("10.00"),
            product_selling_price=_money("154.98"),
        )
        self._add_kit_with_product(kit_name="dup1", product=self.clamp, quantity=6, selling="2.40")
        self._add_kit_with_product(kit_name="dup2", product=self.clamp, quantity=10, selling="2.40")

        self.budget.invalidate_pricing_snapshot_cache()

        raw_products = self.budget._raw_selected_items_total_products_without_shipping()
        self.assertEqual(raw_products.amount, Decimal("503.34"))

        winner_products = _money("309.96") + _money("24.00")
        self.assertEqual(self.budget.selected_items_total_products_without_shipping, winner_products)
        self.assertEqual(self.budget.summary_total_before_benefit_value, winner_products)
        self.assertEqual(self.budget.display_total_base_value, winner_products)
        self.assertEqual(self.budget.display_total_budget_value, winner_products)

    def test_fixed_budget_summary_keeps_operational_catalog_sum(self) -> None:
        warranty_budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 8, 19),
            budget_type=BudgetType.WARRANTY,
            status=BudgetStatus.DRAFT,
            current_step=4,
            slider=0,
        )
        kit = Kit.objects.create(workshop=self.workshop, name="Kit garantia")
        item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=warranty_budget,
            kit=kit,
            quantity=1,
        )
        BudgetKitItemOverride.objects.create(
            workshop=self.workshop,
            budget_item=item,
            product=self.clamp,
            quantity=6,
            product_cost_price=self.clamp.cost_price,
            product_selling_price=_money("2.40"),
        )
        kit_two = Kit.objects.create(workshop=self.workshop, name="Kit garantia 2")
        item_two = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=warranty_budget,
            kit=kit_two,
            quantity=1,
        )
        BudgetKitItemOverride.objects.create(
            workshop=self.workshop,
            budget_item=item_two,
            product=self.clamp,
            quantity=10,
            product_cost_price=self.clamp.cost_price,
            product_selling_price=_money("2.40"),
        )

        warranty_budget.invalidate_pricing_snapshot_cache()

        self.assertEqual(warranty_budget.total_budget_value.amount, Decimal("0.00"))
        self.assertEqual(warranty_budget.selected_items_total_products_without_shipping.amount, Decimal("38.40"))
        self.assertEqual(warranty_budget.summary_total_before_benefit_value.amount, Decimal("38.40"))
        self.assertEqual(warranty_budget.display_total_base_value.amount, Decimal("38.40"))
