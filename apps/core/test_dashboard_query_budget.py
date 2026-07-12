from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.budget.models import Budget
from apps.core.infrastructure.services.dashboard_query_service import _mark_budget_read_only


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
