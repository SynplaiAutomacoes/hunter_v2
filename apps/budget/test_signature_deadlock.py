"""Regression tests for budget approve / signature deadlock decoupling."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase

from apps.accounts.models import Account
from apps.budget.models import Budget, BudgetStatus
from apps.core.infrastructure.services.signature_webhook import process_signature_webhook_payload
from apps.workorder.models import WorkOrder
from apps.workshops.models.workshops import Workshop


class CommissionOrchestratorLockOrderTests(SimpleTestCase):
    @patch("apps.collaborators.commission.orchestrator.WorkOrder.objects")
    @patch("apps.collaborators.commission.orchestrator.transaction.atomic")
    def test_generate_commissions_locks_only_workorder_self(self, atomic_mock: Mock, objects_mock: Mock) -> None:
        from apps.collaborators.commission.orchestrator import WorkOrderCommissionOrchestrator
        from apps.workorder.models import WorkOrderStatus

        atomic_mock.return_value.__enter__ = Mock(return_value=None)
        atomic_mock.return_value.__exit__ = Mock(return_value=False)

        locked = Mock()
        locked.pk = 99
        locked.status = WorkOrderStatus.DRAFT
        locked.budget_type = "sale"
        locked.budget = SimpleNamespace(budget_type="sale")
        locked.collaborators.all.return_value.prefetch_related.return_value = []
        locked.payments.all.return_value = []
        locked._prefetched_objects_cache = {}
        objects_mock.select_for_update.return_value.select_related.return_value.get.return_value = locked

        with patch("apps.collaborators.commission.orchestrator.CollaboratorCommissionEntry.objects") as entry_objects:
            entry_objects.filter.return_value.delete.return_value = None
            WorkOrderCommissionOrchestrator().generate_commissions_for_workorder(workorder=Mock(pk=99))

        objects_mock.select_for_update.assert_called_once_with(of=("self",))
        objects_mock.select_for_update.return_value.select_related.assert_called_once_with("workshop", "budget")


class BudgetApproveDecoupleSyncTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta approve deadlock")
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina approve deadlock",
            cnpj="12.345.678/0001-94",
            phone="+5511999999996",
            address="Rua Approve, 1",
        )

    def test_approve_persists_status_and_workorder_before_sync(self) -> None:
        budget = Budget(workshop=self.workshop, entry_date=date(2026, 9, 1), status=BudgetStatus.WAITING_APPROVAL)
        budget.save()

        with patch.object(WorkOrder, "sync_from_budget", side_effect=RuntimeError("sync boom")) as sync_mock:
            with self.assertRaises(RuntimeError):
                with self.captureOnCommitCallbacks(execute=True):
                    self.assertTrue(budget.approve())

        budget.refresh_from_db()
        self.assertEqual(budget.status, BudgetStatus.APPROVED)
        self.assertTrue(WorkOrder.objects.filter(budget=budget).exists())
        sync_mock.assert_called_once()

    def test_approve_schedules_sync_via_on_commit(self) -> None:
        budget = Budget(workshop=self.workshop, entry_date=date(2026, 9, 2), status=BudgetStatus.WAITING_APPROVAL)
        budget.save()

        with patch.object(WorkOrder, "sync_from_budget") as sync_mock:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                self.assertTrue(budget.approve())
            self.assertGreaterEqual(len(callbacks), 1)
            sync_mock.assert_not_called()
            for callback in callbacks:
                callback()
            sync_mock.assert_called_once()


class SignatureWebhookHealTests(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.patch_find_budget_term = patch(
            "apps.core.infrastructure.services.signature_webhook._find_budget_term_signing",
            return_value=None,
        )
        self.patch_find_wo_term = patch(
            "apps.core.infrastructure.services.signature_webhook._find_workorder_term_signing",
            return_value=None,
        )
        self.patch_find_budget_term.start()
        self.patch_find_wo_term.start()
        self.addCleanup(self.patch_find_budget_term.stop)
        self.addCleanup(self.patch_find_wo_term.stop)

    @patch("apps.workorder.models.WorkOrder.objects.filter")
    @patch("apps.budget.models.Budget.objects.filter")
    def test_already_approved_budget_heals_sync_from_budget(self, budget_filter: Mock, workorder_filter: Mock) -> None:
        workorder = Mock()
        workorder.sync_from_budget = Mock()
        budget = SimpleNamespace(pk=7, approve=Mock(return_value=False), mark_signature_approved=Mock())
        budget_filter.return_value.first.return_value = budget
        # First filter is for matching envelope (budget found); heal uses WorkOrder.objects.filter(budget_id=...).first()
        workorder_filter.return_value.first.side_effect = [None, workorder]

        response = process_signature_webhook_payload(
            payload={"event": "ENVELOPE_COMPLETED", "envelopeId": "env-heal"},
        )

        self.assertEqual(response.status_code, 200)
        budget.mark_signature_approved.assert_called_once()
        workorder.sync_from_budget.assert_called_once()


class WorkOrderApprovalLockOrderTests(SimpleTestCase):
    @patch("apps.workorder.approval.has_unreversed_exit_movements", return_value=True)
    @patch("apps.workorder.approval.WorkOrder.objects")
    @patch("apps.workorder.approval.transaction.atomic")
    def test_approve_workorder_locks_only_workorder_self(
        self,
        atomic_mock: Mock,
        objects_mock: Mock,
        _has_exit: Mock,
    ) -> None:
        from apps.workorder.approval import approve_workorder_with_stock
        from apps.workorder.models import WorkOrderSignatureStatus, WorkOrderStatus

        atomic_mock.return_value.__enter__ = Mock(return_value=None)
        atomic_mock.return_value.__exit__ = Mock(return_value=False)

        locked = Mock()
        locked.pk = 11
        locked.status = WorkOrderStatus.APPROVED
        locked.signature_request_status = WorkOrderSignatureStatus.APPROVED
        locked.budget_type = "sale"
        objects_mock.select_for_update.return_value.select_related.return_value.get.return_value = locked

        workorder = Mock(pk=11)
        workorder.refresh_from_db = Mock()

        with patch("apps.collaborators.commission.allocation.CommissionAllocationService") as alloc_svc:
            alloc_svc.validate.return_value = {"sum": []}
            approve_workorder_with_stock(workorder=workorder, signature_approved=True)

        objects_mock.select_for_update.assert_called_once_with(of=("self",))
        objects_mock.select_for_update.return_value.select_related.assert_called_once_with("workshop", "budget")
