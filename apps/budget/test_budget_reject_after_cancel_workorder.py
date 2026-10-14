from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from djmoney.money import Money

from apps.accounts.models import Account
from apps.budget.models import Budget, BudgetStatus
from apps.collaborators.models import WorkshopCollaborator, WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class BudgetRejectAfterCancelWorkOrderTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Reject Após Cancel OS")
        self.user = User.objects.create_user(username="reject-after-cancel-user", password="secret", cpf="12345678906")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Reject Após Cancel OS",
            cnpj="12.345.678/0001-93",
            phone="+5511999999996",
            address="Rua Reject Cancel, 1",
        )
        role = get_or_create_director_role(account=self.account)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.responsible = WorkshopCollaborator.objects.create(
            workshop=self.workshop,
            name="Responsável Atendimento",
            cpf="12345678907",
            birth_date=date(1990, 1, 1),
            salary=Money(2000, "BRL"),
            admission_date=date(2025, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.ADMINISTRATIVE,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def _create_approved_budget_with_workorder(self, *, workorder_status: str = WorkOrderStatus.DRAFT) -> tuple[Budget, WorkOrder]:
        # Budget.save() on APPROVED get_or_create's the linked WorkOrder.
        budget = Budget(workshop=self.workshop, entry_date=date(2026, 8, 1), status=BudgetStatus.APPROVED, current_step=6)
        budget.save()
        workorder = WorkOrder.objects.get(budget=budget)
        if workorder.status != workorder_status:
            workorder.status = workorder_status
            workorder.save(update_fields=["status"])
        return budget, workorder

    def _post_reject(self, budget: Budget):
        url = reverse("budget:update_budget_status", kwargs={"budget_id": budget.pk, "status": "reject"})
        return self.client.post(
            url,
            {
                "rejection_reason": "Cliente sem condições financeiras.",
                "rejection_responsible_id": str(self.responsible.pk),
            },
        )

    def _post_cancel(self, budget: Budget):
        url = reverse("budget:update_budget_status", kwargs={"budget_id": budget.pk, "status": "cancel"})
        return self.client.post(
            url,
            {
                "cancellation_reason": "Cliente desistiu do serviço.",
                "cancellation_responsible_id": str(self.responsible.pk),
            },
        )

    def test_reject_blocked_when_workorder_is_active(self) -> None:
        budget, _workorder = self._create_approved_budget_with_workorder(workorder_status=WorkOrderStatus.DRAFT)

        response = self._post_reject(budget)

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertIn("Cancele a ordem de serviço primeiro", payload["error"])
        budget.refresh_from_db()
        self.assertEqual(budget.status, BudgetStatus.APPROVED)

    def test_reject_allowed_after_workorder_cancelled(self) -> None:
        budget, _workorder = self._create_approved_budget_with_workorder(workorder_status=WorkOrderStatus.CANCELLED)

        response = self._post_reject(budget)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        budget.refresh_from_db()
        self.assertEqual(budget.status, BudgetStatus.REJECTED)
        self.assertEqual(budget.rejection_reason, "Cliente sem condições financeiras.")
        self.assertEqual(budget.rejection_responsible_id, self.responsible.pk)

    def test_cancel_allowed_after_workorder_cancelled(self) -> None:
        budget, _workorder = self._create_approved_budget_with_workorder(workorder_status=WorkOrderStatus.CANCELLED)

        response = self._post_cancel(budget)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        budget.refresh_from_db()
        self.assertEqual(budget.status, BudgetStatus.CANCELLED)
        self.assertEqual(budget.cancellation_reason, "Cliente desistiu do serviço.")
        self.assertEqual(budget.cancellation_responsible_id, self.responsible.pk)

    def test_approve_still_blocked_when_budget_is_locked(self) -> None:
        budget, _workorder = self._create_approved_budget_with_workorder(workorder_status=WorkOrderStatus.CANCELLED)

        url = reverse("budget:update_budget_status", kwargs={"budget_id": budget.pk, "status": "approve"})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertIn("Reabra o orçamento", payload["error"])
        budget.refresh_from_db()
        self.assertEqual(budget.status, BudgetStatus.APPROVED)
