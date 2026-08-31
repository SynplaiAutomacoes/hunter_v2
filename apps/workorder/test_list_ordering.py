from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

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

    def test_filtered_queryset_orders_by_newest_first(self) -> None:
        first = self._create_workorder(number=10)
        second = self._create_workorder(number=20)
        third = self._create_workorder(number=30)

        request = RequestFactory().get("/workorder/")
        request.user = self.user
        view = WorkOrderListView()
        view.request = request
        view.workshop = self.workshop
        view.kwargs = {}

        ordered_ids = list(view._get_filtered_workorder_queryset().values_list("pk", flat=True))

        self.assertEqual(ordered_ids, [third.pk, second.pk, first.pk])

    def test_reopened_filter_returns_only_open_workorders_reopened_after_delivery(self) -> None:
        reopened = self._create_workorder(number=10)
        reopened.status = WorkOrderStatus.WAITING_DELIVERY
        reopened.delivered_at = timezone.now()
        reopened.reopen_reason = "Corrigir item da O.S."
        reopened.save(update_fields=["status", "delivered_at", "reopen_reason"])

        delivered_again = self._create_workorder(number=20)
        delivered_again.status = WorkOrderStatus.APPROVED
        delivered_again.delivered_at = timezone.now()
        delivered_again.reopen_reason = "Corrigir item da O.S."
        delivered_again.save(update_fields=["status", "delivered_at", "reopen_reason"])

        open_without_delivery = self._create_workorder(number=30)
        open_without_delivery.status = WorkOrderStatus.WAITING_DELIVERY
        open_without_delivery.reopen_reason = "Corrigir item da O.S."
        open_without_delivery.save(update_fields=["status", "reopen_reason"])

        request = RequestFactory().get("/workorder/?reopened=1")
        request.user = self.user
        view = WorkOrderListView()
        view.request = request
        view.workshop = self.workshop
        view.kwargs = {}

        self.assertEqual(list(view._get_filtered_workorder_queryset()), [reopened])
