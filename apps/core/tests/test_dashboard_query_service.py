from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import cast
from unittest.mock import patch

from django.test import SimpleTestCase
from djmoney.money import Money

from apps.budget.models import Budget
from apps.core.domain.services.dashboard_service import DashboardMetrics
from apps.core.infrastructure.services.dashboard_query_service import calculate_average_markup, calculate_markup_progress, run_dashboard_query_task


@dataclass
class MarkupBudgetStub:
    total_budget_value: Money
    total_costs_products_value: Money
    total_costs_services_value: Money


class DashboardMarkupMetricsTests(SimpleTestCase):
    def test_calculate_average_markup_uses_mean_of_approved_budget_markups(self) -> None:
        budgets = [
            MarkupBudgetStub(
                total_budget_value=Money("300.00", "BRL"),
                total_costs_products_value=Money("100.00", "BRL"),
                total_costs_services_value=Money("50.00", "BRL"),
            ),
            MarkupBudgetStub(
                total_budget_value=Money("400.00", "BRL"),
                total_costs_products_value=Money("100.00", "BRL"),
                total_costs_services_value=Money("100.00", "BRL"),
            ),
        ]

        average_markup = calculate_average_markup(cast(list[Budget], budgets))

        self.assertEqual(average_markup, Decimal("2.00"))

    def test_calculate_average_markup_ignores_budgets_without_cost_basis(self) -> None:
        budgets = [
            MarkupBudgetStub(
                total_budget_value=Money("300.00", "BRL"),
                total_costs_products_value=Money("0.00", "BRL"),
                total_costs_services_value=Money("0.00", "BRL"),
            ),
            MarkupBudgetStub(
                total_budget_value=Money("450.00", "BRL"),
                total_costs_products_value=Money("100.00", "BRL"),
                total_costs_services_value=Money("50.00", "BRL"),
            ),
        ]

        average_markup = calculate_average_markup(cast(list[Budget], budgets))

        self.assertEqual(average_markup, Decimal("3.00"))

    def test_dashboard_context_exposes_markup_values(self) -> None:
        context = DashboardMetrics(workshop_id=1, selected_month=6, selected_year=2026, accumulated_markup=Decimal("1.75"), accumulated_markup_progress=88).as_context()

        self.assertEqual(context["markup_acumulado_mes"], Decimal("1.75"))
        self.assertEqual(context["markup_acumulado_progresso"], 88)

    def test_calculate_markup_progress_caps_at_100(self) -> None:
        self.assertEqual(calculate_markup_progress(Decimal("2.50")), 100)

    def test_run_dashboard_query_task_closes_thread_connections(self) -> None:
        with patch("apps.core.infrastructure.services.dashboard_query_service.close_old_connections") as close_old_connections:
            result = run_dashboard_query_task(lambda: "ok")

        self.assertEqual(result, "ok")
        self.assertEqual(close_old_connections.call_count, 2)
