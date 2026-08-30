from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.accounts.models import Account
from apps.budget.models import Budget, BudgetStatus
from apps.collaborators.models import WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workorder.views import WorkOrderListView
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class WorkOrderListOrderingTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Ordenacao OS")
        self.user = User.objects.create_user(username="wo-order-user", password="secret", cpf="12345678907")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Ordenacao OS",
            cnpj="12.345.678/0001-93",
            phone="+5511999999995",
            address="Rua Ordenacao, 1",
        )
        role = get_or_create_director_role(account=self.account)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)

    def _create_workorder(self, *, number: int) -> WorkOrder:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 8, 1),
            status=BudgetStatus.DRAFT,
            number=number,
        )
        return WorkOrder.objects.create(
            workshop=self.workshop,
            budget=budget,
            status=WorkOrderStatus.DRAFT,
            budget_type="sale",
        )

    def test_filtered_queryset_orders_by_budget_number_ascending(self) -> None:
        self._create_workorder(number=30)
        self._create_workorder(number=10)
        self._create_workorder(number=20)

        request = RequestFactory().get("/workorder/")
        request.user = self.user
        view = WorkOrderListView()
        view.request = request
        view.workshop = self.workshop
        view.kwargs = {}

        ordered_numbers = list(
            view._get_filtered_workorder_queryset().values_list("budget__number", flat=True)
        )

        self.assertEqual(ordered_numbers, [10, 20, 30])
