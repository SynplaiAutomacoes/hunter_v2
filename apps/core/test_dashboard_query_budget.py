from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from djmoney.money import Money

from apps.budget.models import Budget
from apps.core.infrastructure.services.dashboard_query_service import (
    _build_injected_pricing_context,
    _mark_budget_read_only,
    _prepare_budget_for_dashboard_pricing,
    _prepare_workorder_for_dashboard_pricing,
)


class KitOverrideReadPathTests(SimpleTestCase):
    def test_workorder_item_uses_prefetched_kit_overrides_without_ensure(self) -> None:
        from apps.workorder.models import WorkOrderItem

        item = WorkOrderItem(kit_id=1)
        override = MagicMock(product_id=10, service_id=None, quantity=2)
        item._prefetched_objects_cache = {"kit_overrides": [override]}

        with patch.object(item, "ensure_kit_snapshot") as ensure_mock:
            products = list(item._iter_frozen_kit_product_overrides())
            maps = item._get_kit_override_maps()

        self.assertEqual(len(products), 1)
        self.assertIn(10, maps[0])
        ensure_mock.assert_not_called()

    def test_budget_item_uses_prefetched_kit_overrides_without_ensure(self) -> None:
        from apps.budget.models import BudgetItem

        item = BudgetItem(kit_id=1)
        override = MagicMock(product_id=7, service_id=None, quantity=1)
        item._prefetched_objects_cache = {"kit_overrides": [override]}

        with patch.object(item, "ensure_kit_snapshot") as ensure_mock:
            products = list(item._iter_frozen_kit_product_overrides())
            maps = item._get_kit_override_maps()

        self.assertEqual(len(products), 1)
        self.assertIn(7, maps[0])
        ensure_mock.assert_not_called()


class ReadOnlyPricingContextTests(SimpleTestCase):
    def test_get_frozen_pricing_context_skips_freeze_when_read_only(self) -> None:
        budget = Budget()
        _mark_budget_read_only(budget)

        with (
            patch.object(type(budget), "has_frozen_pricing_snapshot", new_callable=lambda: property(lambda self: False)),
            patch.object(budget, "freeze_pricing_snapshot") as freeze_mock,
            patch.object(budget, "_get_live_pricing_fallback_context", return_value="live") as live_mock,
        ):
            result = budget.get_frozen_pricing_context()

        self.assertEqual(result, "live")
        freeze_mock.assert_not_called()
        live_mock.assert_called_once()

    def test_injected_pricing_context_short_circuits_live_fallback(self) -> None:
        budget = Budget()
        injected = SimpleNamespace(productive_salary_total=Money(0, "BRL"))
        setattr(budget, "_injected_pricing_context", injected)

        with patch.object(budget, "_get_live_pricing_fallback_context") as live_mock:
            result = budget.get_frozen_pricing_context()

        self.assertIs(result, injected)
        live_mock.assert_not_called()

    def test_live_pricing_fallback_is_cached_per_budget(self) -> None:
        budget = Budget()
        workshop = MagicMock()
        workshop._live_pricing_fallback_by_month = {}

        with (
            patch.object(type(budget), "workshop", new_callable=lambda: property(lambda self: workshop)),
            patch.object(budget, "_get_pricing_reference_date", return_value=MagicMock(month=7, year=2026)),
            patch.object(budget, "_get_reference_workshop_cost", return_value=None) as workshop_cost_mock,
        ):
            first = budget._get_live_pricing_fallback_context()
            second = budget._get_live_pricing_fallback_context()

        self.assertIs(first, second)
        workshop_cost_mock.assert_called_once()

    def test_prepare_budget_skips_labor_only_for_totals_with_slider_zero(self) -> None:
        budget = Budget(slider=0)
        _prepare_budget_for_dashboard_pricing(budget, for_totals_only=True)
        self.assertTrue(getattr(budget, "_skip_mechanic_labor_cost", False))

        budget_cost = Budget(slider=0)
        _prepare_budget_for_dashboard_pricing(budget_cost, for_totals_only=False)
        self.assertFalse(getattr(budget_cost, "_skip_mechanic_labor_cost", False))

    def test_prepare_workorder_mirrors_budget_skip_flag(self) -> None:
        from apps.workorder.models import WorkOrder

        budget = Budget(slider=0)
        workorder = WorkOrder()
        workorder.budget = budget
        _prepare_workorder_for_dashboard_pricing(workorder, for_totals_only=True)
        self.assertTrue(getattr(workorder, "_skip_mechanic_labor_cost", False))

    def test_build_injected_pricing_context_without_workshop_cost(self) -> None:
        workshop = MagicMock()
        context = _build_injected_pricing_context(workshop=workshop, workshop_cost=None)
        self.assertEqual(context.working_hours_per_month, 0)
        self.assertEqual(context.productive_salary_total, Money(0, "BRL"))
