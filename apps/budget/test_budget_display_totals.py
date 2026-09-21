from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from apps.budget.forms.presenters.step5_context import build_step5_context
from apps.budget.models import Budget, BudgetItem, BudgetStatus, BudgetType
from apps.budget.pdf_context import build_budget_pdf_context
from apps.budget.review_totals import build_step4_table_totals, build_step6_table_totals
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.workshops.models.workshops import Workshop


def _money(amount: str) -> Money:
    return Money(amount, "BRL")


class BudgetDisplayTotalsTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Totais Display",
            cnpj="11.222.333/0001-44",
            phone="+5511999999911",
            address="Rua Totais Display, 1",
            uf="SP",
        )
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Totais Display")
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 9, 14),
            budget_type=BudgetType.SALE,
            status=BudgetStatus.DRAFT,
            current_step=5,
            slider=0,
            pricing_reference_month=9,
            pricing_reference_year=2026,
            pricing_hourly_cost_value=_money("164.35"),
            pricing_working_hours_per_month=Decimal("176.00"),
            pricing_productive_salary_total=_money("4938.56"),
            pricing_profitability_multiplier=Decimal("3.30"),
        )
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=self.group,
            code="TD-PECA",
            name="Peca teste",
            unit=Product.Unit.UND,
            cost_price=_money("40.00"),
            selling_price=_money("100.00"),
        )
        self.kit_service = Service.objects.create(
            workshop=self.workshop,
            name="Servico de kit",
            duration=timedelta(minutes=30),
            suggested_cost=_money("10.00"),
            selling_price=_money("320.00"),
        )
        self.long_service = Service.objects.create(
            workshop=self.workshop,
            name="Servico longo",
            duration=timedelta(hours=15),
            suggested_cost=_money("400.00"),
            selling_price=_money("420.00"),
        )
        self.short_service = Service.objects.create(
            workshop=self.workshop,
            name="Servico curto sem venda",
            duration=timedelta(minutes=4),
            suggested_cost=_money("0.00"),
            selling_price=_money("0.00"),
        )

    def _add_kit(self) -> BudgetItem:
        kit = Kit.objects.create(workshop=self.workshop, name="Kit fluido")
        KitService.objects.create(
            kit=kit,
            service=self.kit_service,
            quantity=1,
            duration=timedelta(minutes=30),
            cost_price=_money("10.00"),
            selling_price=_money("320.00"),
        )
        item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            kit=kit,
            quantity=1,
        )
        override = item.kit_overrides.get(service_id=self.kit_service.pk)
        override.quantity = 1
        override.service_selling_price = _money("320.00")
        override.duration = timedelta(minutes=30)
        override.save(update_fields=["quantity", "service_selling_price", "duration"])
        item.refresh_kit_snapshot_totals()
        return item

    def _add_items(self) -> None:
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=self.product,
            quantity=1,
            product_cost_price=_money("40.00"),
            product_selling_price=_money("100.00"),
        )
        self._add_kit()
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            service=self.long_service,
            quantity=1,
            service_cost_price=_money("400.00"),
            service_selling_price=_money("420.00"),
            duration=timedelta(hours=15),
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            service=self.short_service,
            quantity=1,
            service_cost_price=_money("0.00"),
            service_selling_price=_money("0.00"),
            duration=timedelta(minutes=4),
        )
        self.budget.invalidate_pricing_snapshot_cache()

    def test_step4_service_sale_matches_quoted_and_summary_totals(self) -> None:
        self._add_items()
        totals = build_step4_table_totals(budget=self.budget)

        self.assertEqual(totals["services"].sale, _money("740.00"))
        self.assertEqual(self.budget.selected_items_total_services_value, _money("740.00"))
        self.assertEqual(self.budget.total_services_value, _money("740.00"))

    def test_step5_labor_cost_uses_hourly_cost_times_total_duration(self) -> None:
        self._add_items()
        context = build_step5_context(self.budget)
        snapshot_labor = self.budget.pricing_snapshot.total_labor_cost_value

        self.assertEqual(context.custo_total_mao_obra, snapshot_labor)
        self.assertNotEqual(snapshot_labor, self.budget.step4_pricing_breakdown.labor_cost)

    def test_operational_profit_uses_charged_budget_not_traditional_hour(self) -> None:
        self._add_items()
        dados = self.budget.calculate_pricing_methods()
        context = build_step5_context(self.budget)
        charged_total = self.budget.total_budget_value
        costs = self.budget.total_costs_products_value + self.budget.pricing_snapshot.total_labor_cost_value
        expected_profit = charged_total - costs

        self.assertEqual(dados["valor_orcamento"], charged_total)
        self.assertEqual(dados["lucro_operacional"], expected_profit)
        self.assertEqual(context.lucro_operacional, expected_profit)
        self.assertLess(context.lucro_operacional, charged_total)

    def test_warranty_service_sale_stays_excluded_from_table_and_profit(self) -> None:
        item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            service=self.long_service,
            quantity=1,
            service_cost_price=_money("400.00"),
            service_selling_price=_money("420.00"),
            duration=timedelta(hours=1),
        )
        item.item_benefit_type = "warranty"
        item.save(update_fields=["item_benefit_type"])
        self.budget.invalidate_pricing_snapshot_cache()
        totals = build_step4_table_totals(budget=self.budget)

        self.assertEqual(totals["services"].sale, _money("0.00"))
        self.assertLess(totals["services"].profit.amount, Decimal("0.00"))

    def test_zero_duration_third_party_pdf_matches_budget_table(self) -> None:
        labor = Service.objects.create(
            workshop=self.workshop,
            name="Kit embreagem",
            duration=timedelta(hours=8),
            suggested_cost=_money("10.00"),
            selling_price=_money("600.00"),
        )
        third_party = Service.objects.create(
            workshop=self.workshop,
            name="Retifica do Volante",
            duration=timedelta(0),
            suggested_cost=_money("150.00"),
            selling_price=_money("360.00"),
            is_third_party=True,
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            service=labor,
            quantity=1,
            service_cost_price=_money("10.00"),
            service_selling_price=_money("600.00"),
            duration=timedelta(hours=8),
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            service=third_party,
            quantity=1,
            service_cost_price=_money("150.00"),
            service_selling_price=_money("360.00"),
            duration=timedelta(0),
        )
        self.budget.invalidate_pricing_snapshot_cache()

        table = build_step6_table_totals(budget=self.budget)
        step4 = build_step4_table_totals(budget=self.budget)
        pdf = build_budget_pdf_context(budget=self.budget, presentation="selected_items")
        step5 = build_step5_context(self.budget)
        third_party_row = next(row for row in pdf["servicos"] if row["description"] == third_party.name)

        self.assertEqual(table["services"].sale, _money("960.00"))
        self.assertEqual(step4["services"].sale, _money("960.00"))
        self.assertEqual(step5.venda_mao_obra, step4["services"].sale)
        self.assertEqual(step5.venda_servico_terceiros, _money("360.00"))
        self.assertEqual(third_party_row["service_mechanic_cost_price"], _money("0.00"))
        self.assertEqual(pdf["total_services_mechanic_cost_value"], table["services"].cost)
        self.assertEqual(pdf["total_profit_service_value"], table["services"].profit)

    def test_warranty_zero_duration_third_party_stays_sale_zero(self) -> None:
        third_party = Service.objects.create(
            workshop=self.workshop,
            name="Retifica garantia",
            duration=timedelta(0),
            suggested_cost=_money("150.00"),
            selling_price=_money("360.00"),
            is_third_party=True,
        )
        item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            service=third_party,
            quantity=1,
            service_cost_price=_money("150.00"),
            service_selling_price=_money("360.00"),
            duration=timedelta(0),
        )
        item.item_benefit_type = "warranty"
        item.save(update_fields=["item_benefit_type"])
        self.budget.invalidate_pricing_snapshot_cache()

        table = build_step4_table_totals(budget=self.budget)
        pdf = build_budget_pdf_context(budget=self.budget, presentation="selected_items")

        self.assertEqual(table["services"].sale, _money("0.00"))
        self.assertEqual(table["services"].cost, _money("0.00"))
        self.assertEqual(table["services"].profit, _money("0.00"))
        self.assertEqual(pdf["total_services_mechanic_cost_value"], _money("0.00"))
        self.assertEqual(pdf["total_profit_service_value"], _money("0.00"))
