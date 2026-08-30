from decimal import Decimal
from datetime import timedelta
from types import SimpleNamespace

from django.conf import settings
from django.test import SimpleTestCase

if not settings.configured:
    settings.configure(DEFAULT_CURRENCY="BRL")

from djmoney.money import Money

from apps.budget.models import Budget
from apps.budget.pricing import build_pricing_snapshot


class FreightCostPricingTests(SimpleTestCase):
    def test_step_4_summary_does_not_subtract_freight_from_sales_twice(self):
        budget = SimpleNamespace(
            is_fixed_budget=False,
            total_products_value=Money(Decimal("2412.90"), "BRL"),
            total_products_shipping=Money(10, "BRL"),
            total_services_value=Money(0, "BRL"),
            total_services_shipping=Money(30, "BRL"),
        )

        self.assertEqual(
            Budget.selected_items_total_products_without_shipping.fget(budget),
            Money(Decimal("2412.90"), "BRL"),
        )
        self.assertEqual(
            Budget.selected_items_total_services_value.fget(budget),
            Money(0, "BRL"),
        )

    def test_product_and_service_freight_reduce_margin_without_changing_sale_total(self):
        product = SimpleNamespace(id=1, code="P1", application="", location="", name="Peça")
        service = SimpleNamespace(id=2, name="Serviço", is_third_party=True)
        items = [
            SimpleNamespace(
                id=1, product_id=1, service_id=None, kit_id=None, product=product, service=None,
                description="Peça", quantity=1, product_selling_price=Money(100, "BRL"),
                product_cost_price=Money(50, "BRL"), shipping=Money(20, "BRL"), item_benefit_type="normal",
            ),
            SimpleNamespace(
                id=2, product_id=None, service_id=2, kit_id=None, product=None, service=service,
                description="Serviço", quantity=1, service_selling_price=Money(100, "BRL"),
                service_cost_price=Money(40, "BRL"), service_shipping=Money(10, "BRL"),
                item_benefit_type="normal", duration=None,
            ),
        ]

        snapshot = build_pricing_snapshot(
            items=items,
            slider=0,
            discount_value=Money(0, "BRL"),
            discount_percentage=Decimal("0"),
        )

        self.assertEqual(snapshot.total_products_value, Money(100, "BRL"))
        self.assertEqual(snapshot.total_services_value, Money(100, "BRL"))
        self.assertEqual(snapshot.total_budget_value, Money(200, "BRL"))
        self.assertEqual(snapshot.total_products_shipping, Money(20, "BRL"))
        self.assertEqual(snapshot.total_services_shipping, Money(10, "BRL"))
        self.assertEqual(snapshot.product_lines[0].profit_value, Money(30, "BRL"))
        self.assertEqual(snapshot.service_lines[0].profit_value, Money(50, "BRL"))

    def test_labor_cost_uses_consolidated_duration_and_hourly_cost(self):
        service = SimpleNamespace(id=2, name="Serviço", is_third_party=False)
        item = SimpleNamespace(
            id=2,
            product_id=None,
            service_id=2,
            kit_id=None,
            product=None,
            service=service,
            description="Serviço",
            quantity=1,
            service_selling_price=Money(100, "BRL"),
            service_cost_price=Money(0, "BRL"),
            service_shipping=Money(20, "BRL"),
            item_benefit_type="normal",
            duration=timedelta(hours=1, minutes=30),
        )

        snapshot = build_pricing_snapshot(
            items=[item],
            slider=0,
            discount_value=Money(0, "BRL"),
            discount_percentage=Decimal("0"),
            labor_hourly_cost_value=Money(Decimal("28.64"), "BRL"),
        )

        self.assertEqual(snapshot.total_duration, timedelta(hours=1, minutes=30))
        self.assertEqual(snapshot.total_labor_cost_value, Money(Decimal("42.96"), "BRL"))
        self.assertEqual(snapshot.service_lines[0].cost_total, Money(Decimal("42.96"), "BRL"))
        self.assertEqual(snapshot.service_lines[0].profit_value, Money(Decimal("37.04"), "BRL"))

    def test_reported_budget_totals_match_step_5(self):
        direct_product = SimpleNamespace(id=1, code="P1", application="", location="", name="Lâmpada")
        kit_product = SimpleNamespace(id=2, code="P2", application="", location="", name="Parafuso")
        direct_service = SimpleNamespace(id=10, name="Troca da bateria", is_third_party=False)
        kit_services = [SimpleNamespace(id=service_id, name=f"Serviço {service_id}", is_third_party=False) for service_id in range(11, 17)]

        product_override = SimpleNamespace(
            product=kit_product,
            product_id=kit_product.id,
            quantity=1,
            product_selling_price=Money(Decimal("2.92"), "BRL"),
            product_cost_price=Money(Decimal("1.45"), "BRL"),
            shipping=Money(10, "BRL"),
        )
        service_overrides = [
            SimpleNamespace(
                service=service,
                service_id=service.id,
                quantity=1,
                service_selling_price=Money(Decimal("63.35") if index == 5 else Decimal("63.33"), "BRL"),
                service_cost_price=Money(0, "BRL"),
                duration=timedelta(minutes=10),
            )
            for index, service in enumerate(kit_services)
        ]
        kit_item = SimpleNamespace(
            id=3,
            product_id=None,
            service_id=None,
            kit_id=3,
            quantity=1,
            item_benefit_type="normal",
            _iter_frozen_kit_product_overrides=lambda: (product_override,),
            _iter_frozen_kit_service_overrides=lambda: tuple(service_overrides),
        )
        items = [
            SimpleNamespace(
                id=1,
                product_id=direct_product.id,
                service_id=None,
                kit_id=None,
                product=direct_product,
                service=None,
                description=direct_product.name,
                quantity=1,
                product_selling_price=Money(45, "BRL"),
                product_cost_price=Money(Decimal("19.28"), "BRL"),
                shipping=Money(30, "BRL"),
                item_benefit_type="normal",
            ),
            SimpleNamespace(
                id=2,
                product_id=None,
                service_id=direct_service.id,
                kit_id=None,
                product=None,
                service=direct_service,
                description=direct_service.name,
                quantity=1,
                service_selling_price=Money(Decimal("144.39"), "BRL"),
                service_cost_price=Money(0, "BRL"),
                service_shipping=Money(20, "BRL"),
                item_benefit_type="normal",
                duration=timedelta(minutes=30),
            ),
            kit_item,
        ]

        snapshot = build_pricing_snapshot(
            items=items,
            slider=0,
            discount_value=Money(0, "BRL"),
            discount_percentage=Decimal("0"),
            labor_hourly_cost_value=Money(Decimal("28.64"), "BRL"),
        )

        effective_cost = (
            snapshot.total_costs_products_value
            + snapshot.total_products_shipping
            + snapshot.total_labor_cost_value
            + snapshot.total_services_shipping
        )
        operational_profit = snapshot.total_budget_value - effective_cost
        profitability = ((operational_profit.amount / snapshot.total_budget_value.amount) * Decimal("100")).quantize(Decimal("0.01"))
        markup = (snapshot.total_budget_value.amount / effective_cost.amount).quantize(Decimal("0.01"))

        self.assertEqual(snapshot.total_products_by_slider, Money(Decimal("47.92"), "BRL"))
        self.assertEqual(snapshot.total_services_by_slider, Money(Decimal("524.39"), "BRL"))
        self.assertEqual(snapshot.total_budget_value, Money(Decimal("572.31"), "BRL"))
        self.assertEqual(snapshot.total_costs_products_value, Money(Decimal("20.73"), "BRL"))
        self.assertEqual(snapshot.total_products_shipping, Money(40, "BRL"))
        self.assertEqual(snapshot.total_labor_cost_value, Money(Decimal("42.96"), "BRL"))
        self.assertEqual(snapshot.total_services_shipping, Money(20, "BRL"))
        self.assertEqual(effective_cost, Money(Decimal("123.69"), "BRL"))
        self.assertEqual(operational_profit, Money(Decimal("448.62"), "BRL"))
        self.assertEqual(profitability, Decimal("78.39"))
        self.assertEqual(markup, Decimal("4.63"))
