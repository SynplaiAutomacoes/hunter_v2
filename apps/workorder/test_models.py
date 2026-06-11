from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem
from apps.catalog.models.services import Service
from apps.workorder.models import WorkOrder, WorkOrderItem
from apps.workshops.models.workshops import Workshop


class WorkOrderPricingSnapshotTests(TestCase):
    def test_workorder_total_matches_budget_total_for_approved_budget_values(self) -> None:
        workshop = Workshop.objects.create(
            name="Oficina Teste",
            cnpj="19131243000197",
            phone="+5511999999999",
            address="Rua Teste, 123",
            uf="SP",
        )
        service = Service.objects.create(
            workshop=workshop,
            name="Servico de teste",
            description="",
            duration=timedelta(hours=1),
            suggested_cost=Money("40.00", "BRL"),
            selling_price=Money("100.00", "BRL"),
        )
        budget = Budget.objects.create(
            workshop=workshop,
            entry_date=date(2026, 6, 11),
            status="draft",
            current_step=6,
            step5_calculation_viewed=True,
            discount_value=Money("10.00", "BRL"),
            pricing_reference_month=6,
            pricing_reference_year=2026,
            pricing_productive_salary_total=Money("1000.00", "BRL"),
            pricing_working_hours_per_month=Decimal("10.00"),
            pricing_minimum_hourly_cost=Money("80.00", "BRL"),
            pricing_hourly_cost_value=Money("200.00", "BRL"),
            pricing_profitability_multiplier=Decimal("2.50"),
        )
        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            service=service,
            quantity=1,
            service_cost_price=Money("40.00", "BRL"),
            service_selling_price=Money("100.00", "BRL"),
            duration=timedelta(hours=1),
        )
        budget.discount_value = Money("10.00", "BRL")
        budget.save(update_fields=["discount_value"])

        workorder = WorkOrder.objects.create(
            workshop=workshop,
            budget=budget,
            discount_value=budget.resolved_discount_value,
            discount_percentage=budget.resolved_discount_percentage,
        )
        WorkOrderItem.objects.create(
            workshop=workshop,
            workorder=workorder,
            service=service,
            quantity=1,
            service_cost_price=Money("40.00", "BRL"),
            service_selling_price=Money("100.00", "BRL"),
            duration=timedelta(hours=1),
        )

        self.assertEqual(workorder.calculate_pricing_methods(snapshot=workorder._build_pricing_snapshot())["method_name"], "Tradicional")
        self.assertEqual(budget.total_base_value, Money("100.00", "BRL"))
        self.assertEqual(budget.total_budget_value, Money("90.00", "BRL"))
        self.assertEqual(workorder.total_base_value, budget.total_base_value)
        self.assertEqual(workorder.total_budget_value, budget.total_budget_value)
