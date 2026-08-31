from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from django.conf import settings
from django.test import SimpleTestCase

if not settings.configured:
    settings.configure(DEFAULT_CURRENCY="BRL")

from djmoney.money import Money

from apps.budget.review_totals import (
    _accumulate_breakdown,
    _breakdown_from_product_row,
    _breakdown_from_service_row,
    _empty_breakdown,
    _step4_product_row_totals,
    _step4_service_row_totals,
)


class Step4PricingBreakdownTests(SimpleTestCase):
    def test_product_row_totals_include_freight_in_cost_and_profit(self) -> None:
        item = SimpleNamespace(
            is_customer_supplied=False,
            quantity=2,
            product_cost_price=Money("10.00", "BRL"),
            shipping=Money("5.00", "BRL"),
            display_total_price=Money("40.00", "BRL"),
            item_benefit_type="normal",
        )

        totals = _step4_product_row_totals(item=item)

        self.assertEqual(totals.cost, Money("25.00", "BRL"))
        self.assertEqual(totals.sale, Money("40.00", "BRL"))
        self.assertEqual(totals.profit, Money("15.00", "BRL"))

    def test_warranty_product_sale_is_excluded_from_total_de_venda(self) -> None:
        item = SimpleNamespace(
            is_customer_supplied=False,
            quantity=1,
            product_cost_price=Money("30.00", "BRL"),
            shipping=Money("8.00", "BRL"),
            display_total_price=Money("120.00", "BRL"),
            item_benefit_type="warranty",
        )

        totals = _step4_product_row_totals(item=item)

        self.assertEqual(totals.sale, Money("0.00", "BRL"))
        self.assertEqual(totals.profit, Money("-38.00", "BRL"))

    def test_courtesy_service_sale_is_excluded_from_total_de_venda(self) -> None:
        item = SimpleNamespace(
            service=SimpleNamespace(is_third_party=False),
            quantity=1,
            service_cost_price=Money("15.00", "BRL"),
            service_shipping=Money("7.00", "BRL"),
            display_total_price=Money("80.00", "BRL"),
            item_benefit_type="courtesy",
            duration=None,
        )

        totals = _step4_service_row_totals(
            budget=SimpleNamespace(),
            item=item,
            mechanic_cost=Money("15.00", "BRL"),
        )

        self.assertEqual(totals.sale, Money("0.00", "BRL"))
        self.assertEqual(totals.profit, Money("-22.00", "BRL"))

    def test_warranty_product_row_includes_freight_in_total_cost(self) -> None:
        item = SimpleNamespace(
            is_customer_supplied=False,
            quantity=1,
            product_cost_price=Money("30.00", "BRL"),
            shipping=Money("8.00", "BRL"),
            display_total_price=Money("0.00", "BRL"),
            item_benefit_type="warranty",
        )

        totals = _step4_product_row_totals(item=item)

        self.assertEqual(totals.cost, Money("38.00", "BRL"))
        self.assertEqual(totals.profit, Money("-38.00", "BRL"))

    def test_warranty_product_sale_value_does_not_increase_profit(self) -> None:
        item = SimpleNamespace(
            is_customer_supplied=False,
            quantity=1,
            product_cost_price=Money("30.00", "BRL"),
            shipping=Money("8.00", "BRL"),
            display_total_price=Money("120.00", "BRL"),
            item_benefit_type="warranty",
        )

        totals = _step4_product_row_totals(item=item)

        self.assertEqual(totals.sale, Money("0.00", "BRL"))
        self.assertEqual(totals.profit, Money("-38.00", "BRL"))

    def test_service_breakdown_splits_third_party_and_labor(self) -> None:
        budget = SimpleNamespace()
        labor_item = SimpleNamespace(
            service=SimpleNamespace(is_third_party=False),
            quantity=1,
            service_cost_price=Money("0.00", "BRL"),
            service_shipping=Money("4.00", "BRL"),
            duration=timedelta(hours=1),
        )
        third_party_item = SimpleNamespace(
            service=SimpleNamespace(is_third_party=True),
            quantity=1,
            service_cost_price=Money("25.00", "BRL"),
            service_shipping=Money("6.00", "BRL"),
            duration=None,
        )

        labor_breakdown = _breakdown_from_service_row(
            budget=budget,
            item=labor_item,
            mechanic_cost=Money("20.00", "BRL"),
        )
        third_party_breakdown = _breakdown_from_service_row(budget=budget, item=third_party_item)

        combined = _accumulate_breakdown(target=_empty_breakdown(), row=labor_breakdown)
        combined = _accumulate_breakdown(target=combined, row=third_party_breakdown)

        self.assertEqual(combined.labor_cost, Money("20.00", "BRL"))
        self.assertEqual(combined.labor_freight, Money("4.00", "BRL"))
        self.assertEqual(combined.third_party_cost, Money("25.00", "BRL"))
        self.assertEqual(combined.third_party_freight, Money("6.00", "BRL"))
        self.assertEqual(combined.labor_total_cost, Money("24.00", "BRL"))
        self.assertEqual(combined.third_party_total_cost, Money("31.00", "BRL"))

    def test_product_breakdown_accumulates_unit_cost_and_freight(self) -> None:
        breakdown = _breakdown_from_product_row(
            item=SimpleNamespace(
                is_customer_supplied=False,
                quantity=1,
                product_cost_price=Money("12.00", "BRL"),
                shipping=Money("3.00", "BRL"),
            )
        )

        self.assertEqual(breakdown.products_unit_cost, Money("12.00", "BRL"))
        self.assertEqual(breakdown.products_freight, Money("3.00", "BRL"))
        self.assertEqual(breakdown.products_total_cost, Money("15.00", "BRL"))

    def test_service_row_totals_include_freight_for_courtesy_items(self) -> None:
        item = SimpleNamespace(
            service=SimpleNamespace(is_third_party=False),
            quantity=1,
            service_cost_price=Money("15.00", "BRL"),
            service_shipping=Money("7.00", "BRL"),
            display_total_price=Money("0.00", "BRL"),
            item_benefit_type="courtesy",
            duration=None,
        )

        totals = _step4_service_row_totals(
            budget=SimpleNamespace(),
            item=item,
            mechanic_cost=Money("15.00", "BRL"),
        )

        self.assertEqual(totals.cost, Money("22.00", "BRL"))
        self.assertEqual(totals.profit, Money("-22.00", "BRL"))

    def test_courtesy_service_sale_value_does_not_increase_profit(self) -> None:
        item = SimpleNamespace(
            service=SimpleNamespace(is_third_party=False),
            quantity=1,
            service_cost_price=Money("15.00", "BRL"),
            service_shipping=Money("7.00", "BRL"),
            display_total_price=Money("80.00", "BRL"),
            item_benefit_type="courtesy",
            duration=None,
        )

        totals = _step4_service_row_totals(
            budget=SimpleNamespace(),
            item=item,
            mechanic_cost=Money("15.00", "BRL"),
        )

        self.assertEqual(totals.sale, Money("0.00", "BRL"))
        self.assertEqual(totals.profit, Money("-22.00", "BRL"))
