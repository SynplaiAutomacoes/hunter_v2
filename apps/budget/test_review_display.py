from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from django.test import SimpleTestCase
from djmoney.money import Money

from apps.budget.models import Budget
from apps.budget.review_display import build_budget_review_display


class CourtesyKitReviewDisplayTests(SimpleTestCase):
    def test_uses_frozen_service_cost_not_selling_price_as_kit_cost(self) -> None:
        service = SimpleNamespace(is_third_party=False)
        override = SimpleNamespace(
            quantity=1,
            duration=timedelta(hours=1),
            service=service,
            service_selling_price=Money("1494.37", "BRL"),
            service_cost_price=Money("996.46", "BRL"),
            excluded_from_composition=False,
        )
        kit_item = SimpleNamespace(
            product_id=None,
            service_id=None,
            kit_id=1,
            quantity=1,
            item_benefit_type="courtesy",
            is_customer_supplied=False,
            effective_kit_products=[],
            effective_kit_services=[],
            get_kit_products_shipping_total=lambda: Money("0.00", "BRL"),
            get_kit_products_cost_total=lambda: Money("0.00", "BRL"),
            get_kit_products_total=lambda: Money("0.00", "BRL"),
            service_selling_price=Money("1494.37", "BRL"),
            _iter_frozen_kit_product_overrides=lambda: (),
            _iter_frozen_kit_service_overrides=lambda: (override,),
        )
        budget = SimpleNamespace(
            _iter_items=lambda: (kit_item,),
            _is_local_product_item=lambda _item: False,
            _is_local_service_item=lambda _item: False,
            total_labor_cost_value=Money("0.00", "BRL"),
            get_total_labor_by_slider=Money("0.00", "BRL"),
            get_total_products_by_slider_without_shipping=Money("0.00", "BRL"),
            get_total_third_party_by_slider=Money("0.00", "BRL"),
        )

        display = build_budget_review_display(budget=budget)

        self.assertEqual(display.kits[0].allocated_labor_total, Money("1494.37", "BRL"))
        self.assertEqual(display.kits[0].allocated_labor_cost, Money("996.46", "BRL"))


class OperationalDurationTests(SimpleTestCase):
    def test_includes_courtesy_duration_without_changing_chargeable_duration(self) -> None:
        budget = SimpleNamespace(
            total_duration=timedelta(hours=1),
            _iter_items=lambda: (
                SimpleNamespace(item_benefit_type="normal", duration=timedelta(hours=2), quantity=1),
                SimpleNamespace(item_benefit_type="courtesy", duration=timedelta(minutes=10), quantity=40),
            ),
        )

        operational_duration = Budget.operational_total_duration.fget(budget)

        self.assertEqual(operational_duration, timedelta(hours=7, minutes=40))
        self.assertEqual(
            Budget.total_duration_display.fget(SimpleNamespace(operational_total_duration=operational_duration)),
            "07h 40m",
        )
