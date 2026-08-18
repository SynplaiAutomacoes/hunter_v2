from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.budget.models import Budget, BudgetStatus
from apps.collaborators.models import WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class BudgetReopenWorkOrderTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Reabertura WO")
        self.user = User.objects.create_user(username="reopen-wo-user", password="secret", cpf="12345678905")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Reabertura WO",
            cnpj="12.345.678/0001-92",
            phone="+5511999999998",
            address="Rua Reabertura WO, 1",
        )
        role = get_or_create_director_role(account=self.account)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def _create_budget(self, *, status: str = BudgetStatus.APPROVED) -> Budget:
        budget = Budget(workshop=self.workshop, entry_date=date(2026, 8, 1), status=status, current_step=6)
        budget.save()
        return budget

    def _post_reopen(self, budget: Budget) -> int:
        url = reverse("budget:update_budget_status", kwargs={"budget_id": budget.pk, "status": "reopen"})
        response = self.client.post(url, {"reopen_reason": "Correção de itens"})
        return response.status_code

    def test_reopen_blocked_when_workorder_is_finalized(self) -> None:
        budget = self._create_budget()
        WorkOrder.objects.create(
            workshop=self.workshop,
            budget=budget,
            status=WorkOrderStatus.APPROVED,
            budget_type="sale",
        )

        url = reverse("budget:update_budget_status", kwargs={"budget_id": budget.pk, "status": "reopen"})
        response = self.client.post(url, {"reopen_reason": "Correção de itens"})

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertIn("já foi finalizada", payload["error"])
        budget.refresh_from_db()
        self.assertEqual(budget.status, BudgetStatus.APPROVED)

    def test_reopen_allowed_when_workorder_is_open(self) -> None:
        budget = self._create_budget()
        WorkOrder.objects.create(
            workshop=self.workshop,
            budget=budget,
            status=WorkOrderStatus.DRAFT,
            budget_type="sale",
        )

        self.assertEqual(self._post_reopen(budget), 200)
        budget.refresh_from_db()
        self.assertEqual(budget.status, BudgetStatus.WAITING_REVIEW)

    def test_reopen_allowed_when_workorder_is_cancelled(self) -> None:
        budget = self._create_budget()
        WorkOrder.objects.create(
            workshop=self.workshop,
            budget=budget,
            status=WorkOrderStatus.CANCELLED,
            budget_type="sale",
        )

        self.assertEqual(self._post_reopen(budget), 200)
        budget.refresh_from_db()
        self.assertEqual(budget.status, BudgetStatus.WAITING_REVIEW)