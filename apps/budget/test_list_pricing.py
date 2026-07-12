from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from apps.budget.models import Budget
from apps.budget.views.workflow_views import BudgetListView
from apps.workorder.models import WorkOrder
from apps.workorder.views import WorkOrderListView
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Lista Pricing {suffix}",
        cnpj=f"42.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Pricing, 123",
    )


class OperationalListReadOnlyPricingTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.workshop = create_workshop(suffix=1)

    def test_budget_list_marks_read_only_and_does_not_freeze(self) -> None:
        Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 3, 1), slider=0)
        Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 3, 2), slider=0)

        view = BudgetListView()
        view.request = self.factory.get("/budget/")
        view.workshop = self.workshop
        view.kwargs = {}
        view.object_list = view.get_queryset()

        with patch.object(Budget, "freeze_pricing_snapshot") as freeze_mock:
            context = view.get_context_data()
            for budget in context["budget"]:
                self.assertTrue(getattr(budget, "_read_only_pricing_context", False))
                self.assertTrue(getattr(budget, "_skip_mechanic_labor_cost", False))
                _ = budget.total_budget_value

        freeze_mock.assert_not_called()

    def test_workorder_list_marks_read_only_and_does_not_freeze(self) -> None:
        budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 3, 3), slider=0)
        WorkOrder.objects.create(workshop=self.workshop, budget=budget)

        view = WorkOrderListView()
        view.request = self.factory.get("/workorder/")
        view.workshop = self.workshop
        view.kwargs = {}
        view.object_list = view.get_queryset()

        with patch.object(Budget, "freeze_pricing_snapshot") as freeze_mock:
            context = view.get_context_data()
            for workorder in context["workorder"]:
                self.assertTrue(getattr(workorder.budget, "_read_only_pricing_context", False))
                self.assertTrue(getattr(workorder, "_skip_mechanic_labor_cost", False))
                _ = workorder.total_budget_value

        freeze_mock.assert_not_called()
