from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase
from djmoney.money import Money

from apps.budget.discount import split_budget_discount


def _money(amount: str) -> Money:
    return Money(amount, "BRL")


def _budget(*, discount: str, discount_type: str, products: str, labor: str, third_party: str = "0.00") -> SimpleNamespace:
    products_value = _money(products)
    labor_value = _money(labor)
    third_party_value = _money(third_party)
    return SimpleNamespace(
        resolved_discount_value=_money(discount),
        discount_type=discount_type,
        pricing_snapshot=SimpleNamespace(
            total_products_value=products_value,
            total_labor_selling_value=labor_value,
            total_third_party_services_selling=third_party_value,
            total_services_value=labor_value + third_party_value,
        ),
    )


class SplitBudgetDiscountTests(SimpleTestCase):
    def test_products_type_puts_entire_discount_on_parts(self) -> None:
        split = split_budget_discount(budget=_budget(discount="30.00", discount_type="products", products="100.00", labor="50.00"))

        self.assertEqual(split.products, _money("30.00"))
        self.assertEqual(split.labor, _money("0.00"))
        self.assertEqual(split.services, _money("0.00"))

    def test_services_type_puts_entire_discount_on_services(self) -> None:
        split = split_budget_discount(budget=_budget(discount="20.00", discount_type="services", products="100.00", labor="80.00"))

        self.assertEqual(split.products, _money("0.00"))
        self.assertEqual(split.labor, _money("20.00"))
        self.assertEqual(split.services, _money("20.00"))

    def test_both_type_splits_proportionally_like_nfe(self) -> None:
        split = split_budget_discount(budget=_budget(discount="30.00", discount_type="both", products="100.00", labor="50.00"))

        self.assertEqual(split.products, _money("20.00"))
        self.assertEqual(split.labor, _money("10.00"))
        self.assertEqual(split.services, _money("10.00"))
        self.assertEqual(split.products + split.services, _money("30.00"))

    def test_both_type_splits_service_share_between_labor_and_third_party(self) -> None:
        split = split_budget_discount(
            budget=_budget(discount="40.00", discount_type="both", products="100.00", labor="60.00", third_party="40.00"),
        )

        self.assertEqual(split.products, _money("20.00"))
        self.assertEqual(split.services, _money("20.00"))
        self.assertEqual(split.labor, _money("12.00"))
        self.assertEqual(split.third_party, _money("8.00"))
