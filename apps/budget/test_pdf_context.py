from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from djmoney.money import Money

from apps.budget.pdf_context import build_budget_pdf_context
from apps.budget.pricing import ConsolidatedPricingLine, PricingSnapshot, build_pricing_snapshot, zero_money


class BudgetPdfContextTests(SimpleTestCase):
    @staticmethod
    def _build_pdf_budget(snapshot: PricingSnapshot) -> SimpleNamespace:
        return SimpleNamespace(
            pricing_snapshot=snapshot,
            budget_type="sale",
            is_warranty_budget=False,
            discount_type=None,
            selected_items_total_products_without_shipping=snapshot.total_products_value,
            selected_items_total_services_value=snapshot.total_services_value,
            selected_items_total_base_value=snapshot.total_base_value,
            selected_items_total_budget_value=snapshot.total_budget_value,
            workshop=SimpleNamespace(pdf_observation="", name="Oficina Teste"),
            problem_description="",
            observations="",
            customer=SimpleNamespace(name="Cliente Teste"),
            vehicle=SimpleNamespace(plate="ABC1234"),
            criado_em=None,
            budget_status="Aprovado",
        )

    def test_pricing_snapshot_keeps_winner_custom_description_for_duplicate_product(self) -> None:
        product = SimpleNamespace(
            name="Filtro Original",
            code="P1",
            application="Motor",
            location="A1",
            selling_price=Money(80, "BRL"),
            cost_price=Money(40, "BRL"),
        )
        direct_item = SimpleNamespace(
            id=10,
            quantity=3,
            product_id=1,
            service_id=None,
            kit_id=None,
            product=product,
            description="Filtro Premium Personalizado",
            product_selling_price=Money(90, "BRL"),
            product_cost_price=Money(45, "BRL"),
            shipping=zero_money(),
            is_customer_supplied=False,
        )
        kit_item = SimpleNamespace(
            id=20,
            quantity=1,
            product_id=None,
            service_id=None,
            kit_id=5,
            _get_kit_override_maps=lambda: ({}, {}),
            _iter_kit_products=lambda: [SimpleNamespace(product=product, product_id=1, quantity=1)],
            _iter_kit_services=lambda: [],
        )

        snapshot = build_pricing_snapshot(
            items=[direct_item, kit_item],
            slider=0,
            discount_value=zero_money(),
        )

        self.assertEqual(len(snapshot.product_lines), 1)
        self.assertEqual(snapshot.product_lines[0].description, "Filtro Premium Personalizado")
        self.assertEqual(snapshot.product_lines[0].quantity, 3)
        self.assertIs(snapshot.product_lines[0].show_kit_duplicate_warning, True)

    def test_pricing_snapshot_prefers_kit_when_duplicate_product_ties_on_quantity_and_value(self) -> None:
        product = SimpleNamespace(
            name="Filtro Original Kit",
            code="P1",
            application="Motor",
            location="A1",
            selling_price=Money(90, "BRL"),
            cost_price=Money(45, "BRL"),
        )
        direct_item = SimpleNamespace(
            id=10,
            quantity=2,
            product_id=1,
            service_id=None,
            kit_id=None,
            product=product,
            description="Filtro Avulso Personalizado",
            product_selling_price=Money(90, "BRL"),
            product_cost_price=Money(45, "BRL"),
            shipping=zero_money(),
            is_customer_supplied=False,
        )
        kit_item = SimpleNamespace(
            id=20,
            quantity=1,
            product_id=None,
            service_id=None,
            kit_id=5,
            _get_kit_override_maps=lambda: ({}, {}),
            _iter_kit_products=lambda: [SimpleNamespace(product=product, product_id=1, quantity=2)],
            _iter_kit_services=lambda: [],
        )

        snapshot = build_pricing_snapshot(
            items=[direct_item, kit_item],
            slider=0,
            discount_value=zero_money(),
        )

        self.assertEqual(len(snapshot.product_lines), 1)
        self.assertEqual(snapshot.product_lines[0].description, "Filtro Original Kit")
        self.assertEqual(snapshot.product_lines[0].quantity, 2)
        self.assertIs(snapshot.product_lines[0].show_kit_duplicate_warning, True)

    def test_selected_items_pdf_uses_snapshot_lines_for_duplicate_products(self) -> None:
        product_line = ConsolidatedPricingLine(
            line_id="product-1",
            source_item_id=10,
            kind="product",
            entity_id=1,
            description="Filtro de Oleo",
            quantity=3,
            raw_total=Money(300, "BRL"),
            adjusted_total=Money(300, "BRL"),
            cost_total=Money(150, "BRL"),
            has_direct_source=True,
            has_kit_source=True,
        )
        snapshot = PricingSnapshot(
            product_lines=[product_line],
            service_lines=[],
            total_products_shipping=zero_money(),
            total_costs_products_value=Money(150, "BRL"),
            total_products_value=Money(300, "BRL"),
            total_duration=product_line.duration,
            total_third_party_services_cost=zero_money(),
            total_third_party_services_selling=zero_money(),
            total_costs_services_value=zero_money(),
            total_services_value=zero_money(),
            total_labor_cost_value=zero_money(),
            total_labor_selling_value=zero_money(),
            total_labor_by_slider=zero_money(),
            total_products_by_slider=Money(300, "BRL"),
            total_services_by_slider=zero_money(),
            total_base_value=Money(300, "BRL"),
            resolved_discount_value=zero_money(),
            resolved_discount_percentage=Decimal("0.00"),
            total_budget_value=Money(300, "BRL"),
        )
        budget = SimpleNamespace(
            pricing_snapshot=snapshot,
            budget_type="sale",
            is_warranty_budget=False,
            discount_type=None,
            selected_items_total_products_without_shipping=Money(300, "BRL"),
            selected_items_total_services_value=zero_money(),
            selected_items_total_base_value=Money(300, "BRL"),
            selected_items_total_budget_value=Money(300, "BRL"),
            workshop=SimpleNamespace(pdf_observation="", name="Oficina Teste"),
            problem_description="",
            observations="",
            customer=SimpleNamespace(name="Cliente Teste"),
            vehicle=SimpleNamespace(plate="ABC1234"),
            criado_em=None,
            budget_status="Aprovado",
        )

        with patch("apps.budget.pdf_context.build_workshop_logo_data_uri", return_value=""):
            context = build_budget_pdf_context(budget=budget, presentation="selected_items")

        self.assertEqual(len(context["produtos"]), 1)
        self.assertEqual(context["produtos"][0]["description"], "Filtro de Oleo")
        self.assertEqual(context["produtos"][0]["quantity"], 3)
        self.assertEqual(context["produtos"][0]["total_price"], Money(300, "BRL"))
        self.assertIs(context["produtos"][0]["show_kit_duplicate_warning"], True)
        self.assertEqual(context["total_produtos"], Money(300, "BRL"))

    def test_pdf_hides_zero_priced_products_and_services_from_direct_and_kit_sources(self) -> None:
        visible_product = ConsolidatedPricingLine(
            line_id="product-visible",
            source_item_id=1,
            kind="product",
            entity_id=1,
            description="Produto visivel",
            quantity=1,
            raw_total=Money(10, "BRL"),
            adjusted_total=Money(10, "BRL"),
            cost_total=Money(5, "BRL"),
            has_direct_source=True,
        )
        zero_lines = [
            ConsolidatedPricingLine(
                line_id="product-zero-direct",
                source_item_id=2,
                kind="product",
                entity_id=2,
                description="Produto avulso zerado",
                quantity=1,
                raw_total=Money(3, "BRL"),
                adjusted_total=Money(3, "BRL"),
                cost_total=Money(5, "BRL"),
                shipping=Money(3, "BRL"),
                has_direct_source=True,
            ),
            ConsolidatedPricingLine(
                line_id="product-zero-kit",
                source_item_id=3,
                kind="product",
                entity_id=3,
                description="Produto do kit zerado",
                quantity=1,
                raw_total=zero_money(),
                adjusted_total=zero_money(),
                cost_total=Money(5, "BRL"),
                has_kit_source=True,
            ),
            ConsolidatedPricingLine(
                line_id="service-zero-direct",
                source_item_id=4,
                kind="service",
                entity_id=4,
                description="Servico avulso zerado",
                quantity=1,
                raw_total=zero_money(),
                adjusted_total=zero_money(),
                cost_total=Money(5, "BRL"),
                has_direct_source=True,
            ),
            ConsolidatedPricingLine(
                line_id="service-zero-kit",
                source_item_id=5,
                kind="service",
                entity_id=5,
                description="Servico do kit zerado",
                quantity=1,
                raw_total=zero_money(),
                adjusted_total=zero_money(),
                cost_total=Money(5, "BRL"),
                has_kit_source=True,
            ),
        ]
        snapshot = PricingSnapshot(
            product_lines=[visible_product, *zero_lines[:2]],
            service_lines=zero_lines[2:],
            total_products_shipping=zero_money(),
            total_costs_products_value=Money(15, "BRL"),
            total_products_value=Money(10, "BRL"),
            total_duration=visible_product.duration,
            total_third_party_services_cost=zero_money(),
            total_third_party_services_selling=zero_money(),
            total_costs_services_value=Money(10, "BRL"),
            total_services_value=zero_money(),
            total_labor_cost_value=Money(10, "BRL"),
            total_labor_selling_value=zero_money(),
            total_labor_by_slider=zero_money(),
            total_products_by_slider=Money(10, "BRL"),
            total_services_by_slider=zero_money(),
            total_base_value=Money(10, "BRL"),
            resolved_discount_value=zero_money(),
            resolved_discount_percentage=Decimal("0.00"),
            total_budget_value=Money(10, "BRL"),
        )

        with patch("apps.budget.pdf_context.build_workshop_logo_data_uri", return_value=""):
            context = build_budget_pdf_context(budget=self._build_pdf_budget(snapshot))

        self.assertEqual([row["description"] for row in context["produtos"]], ["Produto visivel"])
        self.assertEqual(context["servicos"], [])
        self.assertEqual(context["pages"][0]["produtos"], context["produtos"])
        self.assertEqual(context["pages"][0]["servicos"], context["servicos"])
        self.assertEqual(context["total_profit_product_value"], Money(5, "BRL"))
