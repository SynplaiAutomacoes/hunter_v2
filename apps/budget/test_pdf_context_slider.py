from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem, BudgetItemLocalType
from apps.budget.pdf_context import build_budget_pdf_context
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.workshops.models.workshops import Workshop


class BudgetPdfContextSliderTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina PDF Slider",
            cnpj="11.222.333/0001-44",
            phone="+5511999999999",
            address="Rua PDF, 10",
        )
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo PDF")

    def _create_budget_with_direct_items(self, *, slider: int) -> Budget:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 22),
            current_step=5,
            slider=slider,
        )
        product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="PDF-P-1",
            name="Peca PDF",
            unit=Product.Unit.UND,
            cost_price=Money("50.00", "BRL"),
            selling_price=Money("100.00", "BRL"),
        )
        service = Service.objects.create(
            workshop=self.workshop,
            name="Servico PDF",
            duration=timedelta(hours=1),
            suggested_cost=Money("40.00", "BRL"),
            selling_price=Money("200.00", "BRL"),
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            product=product,
            quantity=1,
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            service=service,
            quantity=1,
        )
        budget.invalidate_pricing_snapshot_cache()
        return budget

    def _create_budget_with_kit(self, *, slider: int) -> Budget:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 22),
            current_step=5,
            slider=slider,
        )
        product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="PDF-KIT-P",
            name="Peca Kit PDF",
            unit=Product.Unit.UND,
            cost_price=Money("30.00", "BRL"),
            selling_price=Money("80.00", "BRL"),
        )
        service = Service.objects.create(
            workshop=self.workshop,
            name="Servico Kit PDF",
            duration=timedelta(hours=1),
            suggested_cost=Money("20.00", "BRL"),
            selling_price=Money("120.00", "BRL"),
        )
        kit = Kit.objects.create(workshop=self.workshop, name="Kit PDF Slider")
        KitProduct.objects.create(kit=kit, product=product, quantity=1)
        KitService.objects.create(kit=kit, service=service, quantity=1, duration=timedelta(hours=1))
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            kit=kit,
            quantity=1,
        )
        budget.invalidate_pricing_snapshot_cache()
        return budget

    def test_pdf_footer_matches_slider_totals_for_direct_items(self) -> None:
        budget = self._create_budget_with_direct_items(slider=-50)
        context = build_budget_pdf_context(budget=budget, presentation="selected_items")

        self.assertEqual(context["total_produtos"], budget.get_total_products_by_slider)
        self.assertEqual(context["total_servicos"], budget.get_total_services_by_slider)
        self.assertEqual(context["desconto"], budget.resolved_discount_value)
        self.assertEqual(context["total_geral"], budget.total_budget_value)
        self.assertNotEqual(budget.get_total_products_by_slider, Money("100.00", "BRL"))
        self.assertNotEqual(budget.get_total_services_by_slider, Money("200.00", "BRL"))
        self.assertEqual(
            context["total_produtos"] + context["total_servicos"] - context["desconto"],
            context["total_geral"],
        )

    def test_pdf_footer_matches_slider_totals_for_kit(self) -> None:
        budget = self._create_budget_with_kit(slider=50)
        context = build_budget_pdf_context(budget=budget, presentation="selected_items")

        self.assertEqual(context["total_produtos"], budget.get_total_products_by_slider)
        self.assertEqual(context["total_servicos"], budget.get_total_services_by_slider)
        self.assertEqual(context["total_geral"], budget.total_budget_value)

        line_products = sum((row["total_price"] for row in context["produtos"]), Money(0, "BRL"))
        line_services = sum((row["total_price"] for row in context["servicos"]), Money(0, "BRL"))
        self.assertEqual(line_products, budget.get_total_products_by_slider)
        self.assertEqual(line_services, budget.get_total_services_by_slider)

    def test_pdf_footer_zero_for_warranty_budget(self) -> None:
        budget = self._create_budget_with_direct_items(slider=25)
        budget.budget_type = "warranty"
        budget.save(update_fields=["budget_type"])
        budget.invalidate_pricing_snapshot_cache()

        context = build_budget_pdf_context(budget=budget, presentation="selected_items")

        self.assertEqual(context["total_geral"], Money("0.00", "BRL"))
        self.assertTrue(context["is_warranty_or_courtesy"])

    def test_local_items_with_slider_keep_footer_consistent(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 22),
            current_step=5,
            slider=-100,
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            is_local=True,
            local_item_type=BudgetItemLocalType.PRODUCT,
            description="Produto local",
            quantity=1,
            product_cost_price=Money("40.00", "BRL"),
            product_selling_price=Money("150.00", "BRL"),
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            is_local=True,
            local_item_type=BudgetItemLocalType.SERVICE,
            description="Servico local",
            quantity=1,
            service_cost_price=Money("30.00", "BRL"),
            service_selling_price=Money("250.00", "BRL"),
            duration=timedelta(hours=1),
        )
        budget.discount_value = Money("10.00", "BRL")
        budget.save(update_fields=["discount_value"])
        budget.invalidate_pricing_snapshot_cache()

        context = build_budget_pdf_context(budget=budget, presentation="selected_items")

        self.assertEqual(context["total_produtos"], budget.get_total_products_by_slider)
        self.assertEqual(context["total_servicos"], budget.get_total_services_by_slider)
        self.assertEqual(context["desconto"], budget.resolved_discount_value)
        self.assertEqual(context["total_geral"], budget.total_budget_value)
        self.assertEqual(context["desconto"].amount, Decimal("10.00"))
