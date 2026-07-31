from __future__ import annotations

from datetime import date

from django.test import RequestFactory, TestCase

from apps.budget.models import Budget
from apps.budget.views.workflow_views import BudgetListView
from apps.workorder.models import WorkOrder
from apps.workorder.views import WorkOrderListView
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Lista {suffix}",
        cnpj=f"41.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


class OperationalListPaginationTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.workshop = create_workshop(suffix=1)

    def test_budget_list_uses_page_sized_queryset(self) -> None:
        for index in range(25):
            Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 1, min(index + 1, 28)))

        view = BudgetListView()
        view.request = self.factory.get("/budget/")
        view.workshop = self.workshop
        view.kwargs = {}

        queryset = view.get_queryset()
        paginator, page, object_list, is_paginated = view.paginate_queryset(queryset, view.paginate_by)

        self.assertTrue(is_paginated)
        self.assertEqual(paginator.per_page, 20)
        self.assertEqual(len(object_list), 20)
        self.assertEqual(page.number, 1)

    def test_workorder_list_uses_page_sized_queryset(self) -> None:
        for index in range(25):
            budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 2, min(index + 1, 28)))
            WorkOrder.objects.create(workshop=self.workshop, budget=budget)

        view = WorkOrderListView()
        view.request = self.factory.get("/workorder/")
        view.workshop = self.workshop
        view.kwargs = {}

        queryset = view.get_queryset()
        paginator, page, object_list, is_paginated = view.paginate_queryset(queryset, view.paginate_by)

        self.assertTrue(is_paginated)
        self.assertEqual(paginator.per_page, 20)
        self.assertEqual(len(object_list), 20)
        self.assertEqual(page.number, 1)
