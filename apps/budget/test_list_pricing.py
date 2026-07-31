from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from djmoney.money import Money

from apps.budget.models import Budget, BudgetStatus, BudgetType
from apps.budget.views.workflow_views import BudgetListView, BudgetStatusReportDataMixin
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workorder.views import WorkOrderListView
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Lista Stored {suffix}",
        cnpj=f"42.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Lista, 123",
    )


class OperationalListStoredTotalTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.workshop = create_workshop(suffix=1)

    def test_budget_list_uses_stored_total_without_pricing_snapshot(self) -> None:
        for index in range(5):
            budget = Budget.objects.create(
                workshop=self.workshop,
                entry_date=date(2026, 3, index + 1),
                budget_type=BudgetType.SALE,
                status=BudgetStatus.DRAFT,
            )
            Budget.objects.filter(pk=budget.pk).update(stored_total_amount=Money(100 + index, "BRL"))

        view = BudgetListView()
        view.request = self.factory.get("/budget/")
        view.workshop = self.workshop
        view.kwargs = {}
        view.object_list = view.get_queryset()

        with patch("apps.budget.pricing.build_pricing_snapshot") as pricing_mock:
            context = view.get_context_data()
            fields = context["fields"]
            value_column = next(column for column in fields if column.label == "Valor Total")
            self.assertEqual(value_column.attr, "stored_total_amount")
            # QuerySet is not materialized/priced in get_context_data.
            self.assertFalse(isinstance(context["budget"], list))
            pricing_mock.assert_not_called()

    def test_workorder_list_uses_stored_total_without_pricing_snapshot(self) -> None:
        for index in range(3):
            budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 3, index + 1))
            workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget)
            WorkOrder.objects.filter(pk=workorder.pk).update(stored_total_amount=Money(50 + index, "BRL"))

        view = WorkOrderListView()
        view.request = self.factory.get("/workorder/")
        view.workshop = self.workshop
        view.kwargs = {}
        view.object_list = view.get_queryset()

        with patch("apps.budget.pricing.build_pricing_snapshot") as pricing_mock:
            context = view.get_context_data()
            fields = context["fields"]
            value_column = next(column for column in fields if column.label == "Valor Total")
            self.assertEqual(value_column.attr, "stored_total_amount")
            self.assertFalse(isinstance(context["workorder"], list))
            pricing_mock.assert_not_called()

    def test_budget_selection_report_sums_stored_totals_via_sql(self) -> None:
        for amount in (Money(100, "BRL"), Money(50, "BRL")):
            budget = Budget.objects.create(
                workshop=self.workshop,
                entry_date=date(2026, 3, 1),
                budget_type=BudgetType.SALE,
                status=BudgetStatus.DRAFT,
            )
            Budget.objects.filter(pk=budget.pk).update(stored_total_amount=amount)

        view = BudgetListView()
        view.request = self.factory.get("/budget/", {"status": BudgetStatus.DRAFT})
        view.workshop = self.workshop

        with CaptureQueriesContext(connection) as ctx:
            report = view._get_selection_report()

        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report["count"], 2)
        self.assertEqual(report["total_value"], Decimal("150.00"))
        # Aggregate path should not load items tables.
        sql_blob = " ".join(query["sql"].lower() for query in ctx.captured_queries)
        self.assertNotIn("budget_budgetitem", sql_blob)

    def test_workorder_selection_report_sums_stored_totals_via_sql(self) -> None:
        for amount in (Money(80, "BRL"), Money(20, "BRL")):
            budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 3, 1))
            workorder = WorkOrder.objects.create(
                workshop=self.workshop,
                budget=budget,
                status=WorkOrderStatus.DRAFT,
            )
            WorkOrder.objects.filter(pk=workorder.pk).update(stored_total_amount=amount)

        view = WorkOrderListView()
        view.request = self.factory.get("/workorder/", {"status": WorkOrderStatus.DRAFT})
        view.workshop = self.workshop

        with CaptureQueriesContext(connection) as ctx:
            report = view._get_selection_report()

        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report["count"], 2)
        self.assertEqual(report["total_value"], Decimal("100.00"))
        sql_blob = " ".join(query["sql"].lower() for query in ctx.captured_queries)
        self.assertNotIn("workorder_workorderitem", sql_blob)

    def test_selection_report_items_skip_pricing_prefetch(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 3, 1),
            status=BudgetStatus.DRAFT,
        )
        Budget.objects.filter(pk=budget.pk).update(stored_total_amount=Money(10, "BRL"))

        mixin = BudgetStatusReportDataMixin()
        mixin.request = self.factory.get("/budget/", {"status": BudgetStatus.DRAFT})
        mixin.workshop = self.workshop

        items = mixin._get_selection_report_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].stored_total_amount.amount, Decimal("10.00"))
