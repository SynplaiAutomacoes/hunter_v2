from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem, BudgetKitItemOverride
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit
from apps.catalog.models.products import Product
from apps.core.infrastructure.services.dashboard_query_service import (
    _BUDGET_ITEMS_PREFETCH,
    _build_injected_pricing_context,
    _mark_budget_read_only,
    _prepare_budget_for_dashboard_pricing,
    _prepare_workorder_for_dashboard_pricing,
)
from apps.workshops.models.workshops import Workshop


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


class DashboardKitOverridePrefetchShapeTests(SimpleTestCase):
    def test_budget_and_workorder_prefetch_select_related_override_catalog_fks(self) -> None:
        from apps.core.infrastructure.kit_prefetch import (
            budget_items_with_kit_prefetch,
            budget_kit_overrides_prefetch,
            workorder_items_with_kit_prefetch,
            workorder_kit_overrides_prefetch,
        )
        from django.db.models import Prefetch

        budget_overrides = budget_kit_overrides_prefetch()
        workorder_overrides = workorder_kit_overrides_prefetch()
        self.assertIn("product", budget_overrides.queryset.query.select_related)
        self.assertIn("service", budget_overrides.queryset.query.select_related)
        self.assertIn("product", workorder_overrides.queryset.query.select_related)
        self.assertIn("service", workorder_overrides.queryset.query.select_related)

        budget_items = budget_items_with_kit_prefetch()
        workorder_items = workorder_items_with_kit_prefetch()
        self.assertTrue(any(isinstance(lookup, Prefetch) and lookup.prefetch_through == "kit_overrides" for lookup in budget_items.queryset._prefetch_related_lookups))
        self.assertTrue(any(isinstance(lookup, Prefetch) and lookup.prefetch_through == "kit_overrides" for lookup in workorder_items.queryset._prefetch_related_lookups))

    def test_dashboard_reexports_use_shared_helpers(self) -> None:
        from apps.core.infrastructure.services.dashboard_query_service import (
            _BUDGET_ITEMS_PREFETCH,
            _BUDGET_KIT_OVERRIDES_PREFETCH,
            _WORKORDER_ITEMS_PREFETCH,
            _WORKORDER_KIT_OVERRIDES_PREFETCH,
        )

        self.assertIn("product", _BUDGET_KIT_OVERRIDES_PREFETCH.queryset.query.select_related)
        self.assertIn("service", _WORKORDER_KIT_OVERRIDES_PREFETCH.queryset.query.select_related)
        self.assertEqual(_BUDGET_ITEMS_PREFETCH.prefetch_through, "items")
        self.assertEqual(_WORKORDER_ITEMS_PREFETCH.prefetch_through, "items")


class DashboardKitOverrideNumQueriesTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Kit Prefetch",
            cnpj="11.222.333/0001-44",
            phone="+5511999999999",
            address="Rua Teste, 123",
        )
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Kit")
        self.kit = Kit.objects.create(workshop=self.workshop, name="Kit Dashboard")
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 1),
            current_step=4,
            slider=0,
        )
        self.item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            kit=self.kit,
            quantity=1,
        )
        for index in range(5):
            product = Product.objects.create(
                workshop=self.workshop,
                group=self.group,
                code=f"KIT-P-{index}",
                name=f"Componente {index}",
                unit=Product.Unit.UND,
                cost_price=Money("5.00", "BRL"),
                selling_price=Money("10.00", "BRL"),
            )
            BudgetKitItemOverride.objects.create(
                workshop=self.workshop,
                budget_item=self.item,
                product=product,
                quantity=1,
                product_cost_price=Money("5.00", "BRL"),
                product_selling_price=Money("10.00", "BRL"),
            )

    def test_prefetched_overrides_do_not_lazy_load_product_fk(self) -> None:
        budget = Budget.objects.filter(pk=self.budget.pk).prefetch_related(_BUDGET_ITEMS_PREFETCH).get()
        item = next(iter(budget._iter_items()))
        overrides = list(item._iter_frozen_kit_product_overrides())
        self.assertEqual(len(overrides), 5)

        with self.assertNumQueries(0):
            for override in overrides:
                self.assertEqual(override.product.workshop_id, self.workshop.pk)
                _ = override.product.name
                _ = override.product.code

    def test_dashboard_total_after_prefetch_avoids_override_fk_queries(self) -> None:
        budget = Budget.objects.filter(pk=self.budget.pk).prefetch_related(_BUDGET_ITEMS_PREFETCH).get()
        _prepare_budget_for_dashboard_pricing(
            budget,
            pricing_context=_build_injected_pricing_context(workshop=self.workshop, workshop_cost=None),
            for_totals_only=True,
        )

        with self.assertNumQueries(0):
            total = budget.total_budget_value

        self.assertEqual(total.amount, Money("50.00", "BRL").amount)

    def test_iter_items_fallback_select_related_override_catalog_fks(self) -> None:
        budget = Budget.objects.get(pk=self.budget.pk)
        # Force the model fallback path (no outer items prefetch cache).
        items = list(budget._iter_items())
        item = items[0]
        overrides = list(item._iter_frozen_kit_product_overrides())
        self.assertEqual(len(overrides), 5)

        with self.assertNumQueries(0):
            for override in overrides:
                _ = override.product.name
                _ = override.product.code


class DashboardStoredTotalPathTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Dashboard Stored",
            cnpj="61.111.222/0001-01",
            phone="+5511777777777",
            address="Rua Dash, 1",
        )

    def test_delivered_workorders_use_stored_total_without_pricing(self) -> None:
        from django.utils import timezone

        from apps.budget.models import Budget, BudgetStatus, BudgetType
        from apps.core.infrastructure.services.dashboard_query_service import DashboardQueryService
        from apps.workorder.models import WorkOrder, WorkOrderStatus

        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 7, 1),
            budget_type=BudgetType.SALE,
            status=BudgetStatus.APPROVED,
        )
        workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=budget,
            status=WorkOrderStatus.APPROVED,
            budget_type="sale",
            delivered_at=timezone.now(),
        )
        WorkOrder.objects.filter(pk=workorder.pk).update(stored_total_amount=Money("123.45", "BRL"))

        with patch("apps.budget.pricing.build_pricing_snapshot") as pricing_mock:
            sale_workorders, warranty_workorders = DashboardQueryService._get_delivered_workorders(
                workshop_id=self.workshop.pk,
                selected_month=timezone.localdate().month,
                selected_year=timezone.localdate().year,
            )

        self.assertEqual(len(sale_workorders), 1)
        self.assertEqual(len(warranty_workorders), 0)
        self.assertEqual(sale_workorders[0].dashboard_display_total.amount, Money("123.45", "BRL").amount)
        pricing_mock.assert_not_called()
