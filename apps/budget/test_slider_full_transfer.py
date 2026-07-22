from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase
from djmoney.money import Money

from apps.budget.pricing import build_pricing_snapshot


class BudgetSliderFullTransferTests(SimpleTestCase):
    def _build_items(self) -> list[SimpleNamespace]:
        product_item = SimpleNamespace(
            id=1,
            quantity=1,
            product_id=1,
            service_id=None,
            kit_id=None,
            is_local=False,
            is_customer_supplied=False,
            item_benefit_type="normal",
            description="Peca",
            product_selling_price=Money("100.00", "BRL"),
            product_cost_price=Money("50.00", "BRL"),
            shipping=Money("0.00", "BRL"),
            product=SimpleNamespace(id=1, code="P", application="", location="", name="Peca"),
            service=None,
            kit=None,
            duration=None,
            service_selling_price=Money(0, "BRL"),
            service_cost_price=Money(0, "BRL"),
            service_shipping=Money(0, "BRL"),
        )
        labor_item = SimpleNamespace(
            id=2,
            quantity=1,
            product_id=None,
            service_id=2,
            kit_id=None,
            is_local=False,
            is_customer_supplied=False,
            item_benefit_type="normal",
            description="MO",
            product_selling_price=Money(0, "BRL"),
            product_cost_price=Money(0, "BRL"),
            shipping=Money(0, "BRL"),
            product=None,
            service=SimpleNamespace(id=2, is_third_party=False, name="MO", shipping=Money("10.00", "BRL")),
            kit=None,
            duration=timedelta(hours=1),
            service_selling_price=Money("200.00", "BRL"),
            service_cost_price=Money("50.00", "BRL"),
            service_shipping=Money("10.00", "BRL"),
        )
        third_party_item = SimpleNamespace(
            id=3,
            quantity=1,
            product_id=None,
            service_id=3,
            kit_id=None,
            is_local=False,
            is_customer_supplied=False,
            item_benefit_type="normal",
            description="Terceiro",
            product_selling_price=Money(0, "BRL"),
            product_cost_price=Money(0, "BRL"),
            shipping=Money(0, "BRL"),
            product=None,
            service=SimpleNamespace(id=3, is_third_party=True, name="Terceiro", shipping=Money(0, "BRL")),
            kit=None,
            duration=timedelta(hours=2),
            service_selling_price=Money("925.96", "BRL"),
            service_cost_price=Money("122.46", "BRL"),
            service_shipping=Money(0, "BRL"),
        )
        return [product_item, labor_item, third_party_item]

    @staticmethod
    def _is_product(item: SimpleNamespace) -> bool:
        return item.product_id is not None

    @staticmethod
    def _is_service(item: SimpleNamespace) -> bool:
        return item.service_id is not None

    def test_slider_minus_100_moves_all_service_profit_to_products(self) -> None:
        labor_cost = Money("50.00", "BRL")
        snapshot = build_pricing_snapshot(
            items=self._build_items(),
            slider=-100,
            discount_value=Money("0.00", "BRL"),
            discount_percentage=Decimal("0"),
            labor_cost_value=labor_cost,
            is_local_product_item=self._is_product,
            is_local_service_item=self._is_service,
        )

        expected_services_floor = labor_cost + Money("10.00", "BRL") + Money("122.46", "BRL")
        self.assertEqual(snapshot.total_labor_by_slider, labor_cost)
        self.assertEqual(snapshot.total_third_party_by_slider, Money("122.46", "BRL"))
        self.assertEqual(snapshot.total_services_by_slider, expected_services_floor)
        self.assertEqual(snapshot.total_products_by_slider, Money("1053.50", "BRL"))
        self.assertEqual(snapshot.total_base_value, Money("1235.96", "BRL"))

    def test_slider_plus_100_keeps_third_party_selling_and_moves_product_profit_to_labor(self) -> None:
        labor_cost = Money("50.00", "BRL")
        snapshot = build_pricing_snapshot(
            items=self._build_items(),
            slider=100,
            discount_value=Money("0.00", "BRL"),
            discount_percentage=Decimal("0"),
            labor_cost_value=labor_cost,
            is_local_product_item=self._is_product,
            is_local_service_item=self._is_service,
        )

        self.assertEqual(snapshot.total_products_by_slider, Money("50.00", "BRL"))
        self.assertEqual(snapshot.total_third_party_by_slider, Money("925.96", "BRL"))
        self.assertEqual(snapshot.total_labor_by_slider, Money("250.00", "BRL"))
        self.assertEqual(snapshot.total_base_value, Money("1235.96", "BRL"))

    def test_slider_minus_100_uses_hunter_floor_even_when_service_cost_equals_selling(self) -> None:
        """Regression from production prints: MO stayed at selling when line costs ~= selling."""
        product_item = SimpleNamespace(
            id=1,
            quantity=1,
            product_id=1,
            service_id=None,
            kit_id=None,
            is_local=False,
            is_customer_supplied=False,
            item_benefit_type="normal",
            description="Peca",
            product_selling_price=Money("2072.15", "BRL"),
            product_cost_price=Money("2072.15", "BRL"),
            shipping=Money("0.00", "BRL"),
            product=SimpleNamespace(id=1, code="P", application="", location="", name="Peca"),
            service=None,
            kit=None,
            duration=None,
            service_selling_price=Money(0, "BRL"),
            service_cost_price=Money(0, "BRL"),
            service_shipping=Money(0, "BRL"),
        )
        labor_item = SimpleNamespace(
            id=2,
            quantity=1,
            product_id=None,
            service_id=2,
            kit_id=None,
            is_local=False,
            is_customer_supplied=False,
            item_benefit_type="normal",
            description="MO",
            product_selling_price=Money(0, "BRL"),
            product_cost_price=Money(0, "BRL"),
            shipping=Money(0, "BRL"),
            product=None,
            service=SimpleNamespace(id=2, is_third_party=False, name="MO", shipping=Money("10.00", "BRL")),
            kit=None,
            duration=timedelta(hours=4, minutes=48),
            # Line cost equals selling — old fallback used this as floor and blocked transfer.
            service_selling_price=Money("1115.96", "BRL"),
            service_cost_price=Money("1115.96", "BRL"),
            service_shipping=Money("10.00", "BRL"),
        )
        hunter_labor_cost = Money("172.46", "BRL")
        snapshot = build_pricing_snapshot(
            items=[product_item, labor_item],
            slider=-100,
            discount_value=Money("0.00", "BRL"),
            discount_percentage=Decimal("0"),
            labor_cost_value=hunter_labor_cost,
            is_local_product_item=self._is_product,
            is_local_service_item=self._is_service,
        )

        self.assertEqual(snapshot.total_labor_by_slider, hunter_labor_cost)
        self.assertEqual(snapshot.total_services_by_slider, Money("182.46", "BRL"))
        self.assertEqual(snapshot.total_products_by_slider, Money("3015.65", "BRL"))
        self.assertEqual(snapshot.total_base_value, Money("3198.11", "BRL"))
