from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.budget.models import Budget, BudgetStatus
from apps.collaborators.models import WorkshopCollaborator, WorkshopMember
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

    def _create_administrative_collaborator(self, *, workshop: Workshop | None = None, is_active: bool = True) -> WorkshopCollaborator:
        return WorkshopCollaborator.objects.create(
            workshop=workshop or self.workshop,
            name="Responsável Administrativo",
            cpf="52998224725",
            birth_date=date(1990, 1, 1),
            admission_date=date(2020, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.ADMINISTRATIVE,
            is_active=is_active,
        )

    def _post_status(self, budget: Budget, status: str, data: dict[str, str]) -> object:
        url = reverse("budget:update_budget_status", kwargs={"budget_id": budget.pk, "status": status})
        return self.client.post(url, data)

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

    def test_cancel_persists_active_administrative_responsible(self) -> None:
        budget = self._create_budget(status=BudgetStatus.DRAFT)
        responsible = self._create_administrative_collaborator()

        response = self._post_status(
            budget,
            "cancel",
            {"cancellation_reason": "Cliente desistiu", "cancellation_responsible_id": str(responsible.pk)},
        )

        self.assertEqual(response.status_code, 200)
        budget.refresh_from_db()
        self.assertEqual(budget.status, BudgetStatus.CANCELLED)
        self.assertEqual(budget.cancellation_responsible, responsible)

    def test_reject_requires_administrative_responsible(self) -> None:
        budget = self._create_budget(status=BudgetStatus.DRAFT)

        response = self._post_status(budget, "reject", {"rejection_reason": "Cliente não aprovou"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("responsável pelo atendimento", response.json()["error"])

    def test_reject_rejects_inactive_administrative_responsible(self) -> None:
        budget = self._create_budget(status=BudgetStatus.DRAFT)
        responsible = self._create_administrative_collaborator(is_active=False)

        response = self._post_status(
            budget,
            "reject",
            {"rejection_reason": "Cliente não aprovou", "rejection_responsible_id": str(responsible.pk)},
        )

        self.assertEqual(response.status_code, 400)
        budget.refresh_from_db()
        self.assertEqual(budget.status, BudgetStatus.DRAFT)
