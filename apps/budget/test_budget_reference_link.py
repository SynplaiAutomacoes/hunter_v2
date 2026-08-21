from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.budget.models import Budget, BudgetStatus
from apps.budget.services.budget_linking_service import LINKED_COPY_CLOSED_WORKORDER_MESSAGE
from apps.collaborators.models import WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.workorder.models import WORKORDER_OPEN_STATUSES, WorkOrderStatus
from apps.workshops.models.workshops import Workshop

User = get_user_model()

CLOSED_WORKORDER_STATUSES = (
    WorkOrderStatus.REJECTED,
    WorkOrderStatus.CANCELLED,
    WorkOrderStatus.APPROVED,
)


class BudgetReferenceLinkTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Vinculo Referencia")
        self.user = User.objects.create_user(username="ref-link-user", password="secret", cpf="12345678906")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Vinculo Referencia",
            cnpj="12.345.678/0001-93",
            phone="+5511999999997",
            address="Rua Vinculo Referencia, 1",
        )
        role = get_or_create_director_role(account=self.account)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def _create_budget_with_workorder(self, *, workorder_status: str) -> Budget:
        budget = Budget(
            workshop=self.workshop,
            entry_date=date(2026, 8, 1),
            status=BudgetStatus.APPROVED,
            current_step=6,
        )
        budget.save()
        workorder = budget.workorders.get()
        if workorder.status != workorder_status:
            workorder.status = workorder_status
            workorder.save(update_fields=["status"])
        return budget

    def _reference_url(self, budget: Budget) -> str:
        return reverse("budget:budget_reference_modal", kwargs={"pk": budget.pk})

    def test_post_relate_yes_blocked_when_workorder_is_closed(self) -> None:
        for status in CLOSED_WORKORDER_STATUSES:
            with self.subTest(status=status):
                budget = self._create_budget_with_workorder(workorder_status=status)
                budget_count = Budget.objects.count()

                response = self.client.post(self._reference_url(budget), {"relate_budget": "yes"})

                self.assertEqual(response.status_code, 400)
                self.assertIn(LINKED_COPY_CLOSED_WORKORDER_MESSAGE.encode(), response.content)
                self.assertEqual(Budget.objects.count(), budget_count)

    def test_post_relate_yes_allowed_when_workorder_is_open(self) -> None:
        for status in WORKORDER_OPEN_STATUSES:
            with self.subTest(status=status):
                budget = self._create_budget_with_workorder(workorder_status=status)

                response = self.client.post(self._reference_url(budget), {"relate_budget": "yes"})

                self.assertEqual(response.status_code, 200)
                new_budget = Budget.objects.exclude(pk=budget.pk).latest("pk")
                self.assertEqual(new_budget.reference_budget_id, budget.pk)

    def test_post_relate_no_blocked_when_workorder_is_closed(self) -> None:
        budget = self._create_budget_with_workorder(workorder_status=WorkOrderStatus.APPROVED)
        budget_count = Budget.objects.count()

        response = self.client.post(self._reference_url(budget), {"relate_budget": "no"})

        self.assertEqual(response.status_code, 400)
        self.assertIn(LINKED_COPY_CLOSED_WORKORDER_MESSAGE.encode(), response.content)
        self.assertEqual(Budget.objects.count(), budget_count)

    def test_get_modal_does_not_offer_link_when_workorder_is_closed(self) -> None:
        budget = self._create_budget_with_workorder(workorder_status=WorkOrderStatus.REJECTED)

        response = self.client.get(self._reference_url(budget))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, LINKED_COPY_CLOSED_WORKORDER_MESSAGE)
        self.assertContains(response, "Vínculo indisponível")
        self.assertNotContains(response, 'name="relate_budget"')
        self.assertNotContains(response, "Finalizar cópia")
        self.assertContains(response, "Fechar")

    def test_get_modal_offers_link_when_workorder_is_open(self) -> None:
        budget = self._create_budget_with_workorder(workorder_status=WorkOrderStatus.DRAFT)

        response = self.client.get(self._reference_url(budget))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="yes"')
        self.assertNotContains(response, LINKED_COPY_CLOSED_WORKORDER_MESSAGE)
