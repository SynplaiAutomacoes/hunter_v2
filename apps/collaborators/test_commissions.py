from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import PropertyMock, patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget, BudgetStatus
from apps.collaborators.models import CollaboratorCommissionEntry, CollaboratorPayroll, CollaboratorPayrollItem, WorkshopCollaborator
from apps.collaborators.services import sync_workorder_collaborator_payrolls
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.views.payroll import _mark_payroll_as_paid, _mark_payroll_commissions_as_paid, _unmark_payroll_commissions_as_paid
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Comissão {suffix}",
        cnpj=f"51.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Comissão, 123",
    )


def create_collaborator(*, workshop: Workshop, suffix: int) -> WorkshopCollaborator:
    return WorkshopCollaborator.objects.create(
        workshop=workshop,
        name=f"Colaborador {suffix}",
        cpf=f"1234567890{suffix}",
        birth_date=date(1990, 1, 1),
        salary=Money(2000, "BRL"),
        admission_date=date(2025, 1, 1),
        collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
        receives_commission=True,
        commission_percentage=Decimal("0.100000"),
    )


def create_workorder(*, workshop: Workshop, budget_type: str, status: str = WorkOrderStatus.APPROVED) -> WorkOrder:
    budget = Budget.objects.create(
        workshop=workshop,
        entry_date=date(2026, 1, 10),
        status=BudgetStatus.APPROVED,
        budget_type=budget_type,
    )
    return WorkOrder.objects.create(
        workshop=workshop,
        budget=budget,
        status=status,
        budget_type=budget_type,
    )


class CollaboratorCommissionSyncTests(TestCase):
    def test_sale_workorder_generates_commission_but_courtesy_and_warranty_do_not(self) -> None:
        workshop = create_workshop(suffix=1)
        collaborator = create_collaborator(workshop=workshop, suffix=1)
        sale_workorder = create_workorder(workshop=workshop, budget_type="sale")
        courtesy_workorder = create_workorder(workshop=workshop, budget_type="courtesy")
        warranty_workorder = create_workorder(workshop=workshop, budget_type="warranty")
        sale_workorder.collaborators.add(collaborator)
        courtesy_workorder.collaborators.add(collaborator)
        warranty_workorder.collaborators.add(collaborator)

        with patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money(1000, "BRL")):
            sync_workorder_collaborator_payrolls(workorder=sale_workorder)
            sync_workorder_collaborator_payrolls(workorder=courtesy_workorder)
            sync_workorder_collaborator_payrolls(workorder=warranty_workorder)

        self.assertTrue(CollaboratorCommissionEntry.objects.filter(workorder=sale_workorder, collaborator=collaborator).exists())
        self.assertFalse(CollaboratorCommissionEntry.objects.filter(workorder=courtesy_workorder, collaborator=collaborator).exists())
        self.assertFalse(CollaboratorCommissionEntry.objects.filter(workorder=warranty_workorder, collaborator=collaborator).exists())

    def test_reopened_workorder_removes_pending_commission_and_preserves_paid_commission(self) -> None:
        workshop = create_workshop(suffix=2)
        collaborator = create_collaborator(workshop=workshop, suffix=2)
        pending_workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        paid_workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.DRAFT)
        pending_workorder.collaborators.add(collaborator)
        paid_workorder.collaborators.add(collaborator)
        pending_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=pending_workorder,
            reference_year=2026,
            reference_month=1,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )
        paid_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=paid_workorder,
            reference_year=2026,
            reference_month=1,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.PAID,
            paid_at=date(2026, 1, 20),
        )

        sync_workorder_collaborator_payrolls(workorder=pending_workorder)
        sync_workorder_collaborator_payrolls(workorder=paid_workorder)

        self.assertFalse(CollaboratorCommissionEntry.objects.filter(pk=pending_entry.pk).exists())
        self.assertTrue(CollaboratorCommissionEntry.objects.filter(pk=paid_entry.pk, status=CollaboratorCommissionEntry.Status.PAID).exists())

    def test_paid_commission_remains_after_reopen_and_reapprove_without_duplicate(self) -> None:
        workshop = create_workshop(suffix=22)
        collaborator = create_collaborator(workshop=workshop, suffix=22)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)
        workorder.collaborators.add(collaborator)
        paid_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=workorder,
            reference_year=2026,
            reference_month=1,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.PAID,
            paid_at=date(2026, 1, 20),
        )

        with patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money(1500, "BRL")):
            workorder.status = WorkOrderStatus.DRAFT
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 1, 1))

            paid_entry.refresh_from_db()
            self.assertEqual(paid_entry.status, CollaboratorCommissionEntry.Status.PAID)
            self.assertEqual(paid_entry.base_amount, Money(1000, "BRL"))
            self.assertEqual(paid_entry.commission_amount, Money(100, "BRL"))

            workorder.status = WorkOrderStatus.APPROVED
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 1, 1))

        paid_entry.refresh_from_db()
        self.assertEqual(CollaboratorCommissionEntry.objects.filter(workorder=workorder, collaborator=collaborator).count(), 1)
        self.assertEqual(paid_entry.pk, CollaboratorCommissionEntry.objects.get(workorder=workorder, collaborator=collaborator).pk)
        self.assertEqual(paid_entry.status, CollaboratorCommissionEntry.Status.PAID)
        self.assertEqual(paid_entry.base_amount, Money(1000, "BRL"))
        self.assertEqual(paid_entry.commission_amount, Money(100, "BRL"))
        self.assertEqual(paid_entry.paid_at, date(2026, 1, 20))

    def test_reapprove_after_cancel_reopen_flow_generates_one_commission(self) -> None:
        workshop = create_workshop(suffix=3)
        collaborator = create_collaborator(workshop=workshop, suffix=3)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)
        workorder.collaborators.add(collaborator)

        with patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money(1000, "BRL")):
            sync_workorder_collaborator_payrolls(workorder=workorder)
            workorder.status = WorkOrderStatus.DRAFT
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder)
            workorder.status = WorkOrderStatus.CANCELLED
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder)
            workorder.status = WorkOrderStatus.DRAFT
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder)
            workorder.status = WorkOrderStatus.APPROVED
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder)

        self.assertEqual(CollaboratorCommissionEntry.objects.filter(workorder=workorder, collaborator=collaborator).count(), 1)

    def test_paid_payroll_still_resyncs_commission_after_reopen_cancel_reapprove_flow(self) -> None:
        workshop = create_workshop(suffix=31)
        collaborator = create_collaborator(workshop=workshop, suffix=31)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)
        workorder.collaborators.add(collaborator)
        workorder.criado_em = timezone.make_aware(datetime(2026, 1, 2, 10, 0, 0))
        workorder.save(update_fields=["criado_em"])

        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=1,
            due_date=date(2026, 1, 5),
            salary_amount=Money(2000, "BRL"),
            transport_allowance_amount=Money(0, "BRL"),
            benefits_amount=Money(0, "BRL"),
            commission_amount=Money(0, "BRL"),
            total_amount=Money(2000, "BRL"),
        )
        movement = FinancialMovement.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            direction=FinancialMovement.MovementDirection.DEBIT,
            description="Folha paga",
            amount=Money(2000, "BRL"),
            due_date=date(2026, 1, 5),
            is_paid=True,
        )
        payroll.financial_movement = movement
        payroll.save(update_fields=["financial_movement"])

        with patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money(1000, "BRL")):
            workorder.status = WorkOrderStatus.DRAFT
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 1, 1))

            workorder.status = WorkOrderStatus.CANCELLED
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 1, 1))

            workorder.status = WorkOrderStatus.DRAFT
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 1, 1))

            workorder.status = WorkOrderStatus.APPROVED
            workorder.save(update_fields=["status"])
            sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 1, 1))

        entry = CollaboratorCommissionEntry.objects.get(workorder=workorder, collaborator=collaborator)
        payroll.refresh_from_db()
        movement.refresh_from_db()

        self.assertEqual(entry.status, CollaboratorCommissionEntry.Status.PAID)
        self.assertIsNotNone(entry.paid_at)
        self.assertEqual(entry.payroll_id, payroll.pk)
        self.assertEqual(payroll.commission_amount, Money(100, "BRL"))
        self.assertEqual(payroll.total_amount, Money(2100, "BRL"))
        self.assertTrue(movement.is_paid)
        self.assertEqual(movement.amount, Money(2100, "BRL"))

    def test_reopened_workorder_keeps_paid_commission_in_unpaid_payroll_totals(self) -> None:
        workshop = create_workshop(suffix=32)
        collaborator = create_collaborator(workshop=workshop, suffix=32)
        workorder = create_workorder(workshop=workshop, budget_type="sale", status=WorkOrderStatus.APPROVED)
        workorder.collaborators.add(collaborator)
        workorder.criado_em = timezone.make_aware(datetime(2026, 1, 2, 10, 0, 0))
        workorder.save(update_fields=["criado_em"])

        with patch("apps.workorder.models.WorkOrder.total_services_value", new_callable=PropertyMock, return_value=Money(1000, "BRL")):
            payroll = sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 1, 1))[0]

        entry = CollaboratorCommissionEntry.objects.get(workorder=workorder, collaborator=collaborator)
        entry.status = CollaboratorCommissionEntry.Status.PAID
        entry.paid_at = date(2026, 1, 20)
        entry.save(update_fields=["status", "paid_at"])

        workorder.status = WorkOrderStatus.DRAFT
        workorder.save(update_fields=["status"])
        sync_workorder_collaborator_payrolls(workorder=workorder, reference_date=date(2026, 1, 1))

        entry.refresh_from_db()
        payroll.refresh_from_db()

        self.assertEqual(entry.status, CollaboratorCommissionEntry.Status.PAID)
        self.assertEqual(payroll.commission_amount, Money(100, "BRL"))
        self.assertEqual(payroll.total_amount, Money(2100, "BRL"))
        self.assertEqual(payroll.items.filter(item_type=CollaboratorPayrollItem.ItemType.COMMISSION).count(), 1)

    def test_mark_payroll_commissions_as_paid_respects_month_boundary(self) -> None:
        workshop = create_workshop(suffix=4)
        collaborator = create_collaborator(workshop=workshop, suffix=4)
        wo1 = create_workorder(workshop=workshop, budget_type="sale")
        wo2 = create_workorder(workshop=workshop, budget_type="sale")
        wo1.collaborators.add(collaborator)
        wo2.collaborators.add(collaborator)

        payroll_m6 = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=6,
            due_date=date(2026, 6, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )

        m6_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=wo1,
            payroll=payroll_m6,
            reference_year=2026,
            reference_month=6,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )
        m7_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=wo2,
            payroll=payroll_m6,
            reference_year=2026,
            reference_month=7,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )

        _mark_payroll_commissions_as_paid(payroll=payroll_m6)

        m6_entry.refresh_from_db()
        m7_entry.refresh_from_db()

        self.assertEqual(m6_entry.status, CollaboratorCommissionEntry.Status.PAID)
        self.assertIsNotNone(m6_entry.paid_at)
        self.assertEqual(
            m7_entry.status,
            CollaboratorCommissionEntry.Status.FORECAST,
            "Month 7 commission should NOT be marked as paid when paying month 6 payroll",
        )
        self.assertIsNone(m7_entry.paid_at)

    def test_unmark_payroll_commissions_reverts_status_and_respects_month_boundary(self) -> None:
        workshop = create_workshop(suffix=5)
        collaborator = create_collaborator(workshop=workshop, suffix=5)
        wo1 = create_workorder(workshop=workshop, budget_type="sale")
        wo2 = create_workorder(workshop=workshop, budget_type="sale")
        wo1.collaborators.add(collaborator)
        wo2.collaborators.add(collaborator)

        payroll_m6 = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=6,
            due_date=date(2026, 6, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )

        m6_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=wo1,
            payroll=payroll_m6,
            reference_year=2026,
            reference_month=6,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.PAID,
            paid_at=date(2026, 6, 5),
        )
        m7_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=wo2,
            payroll=payroll_m6,
            reference_year=2026,
            reference_month=7,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.PAID,
            paid_at=date(2026, 7, 5),
        )

        _unmark_payroll_commissions_as_paid(payroll=payroll_m6)

        m6_entry.refresh_from_db()
        m7_entry.refresh_from_db()

        self.assertEqual(
            m6_entry.status,
            CollaboratorCommissionEntry.Status.FORECAST,
            "Month 6 commission should revert to FORECAST when month 6 payroll is unpaid",
        )
        self.assertIsNone(m6_entry.paid_at)
        self.assertEqual(
            m7_entry.status,
            CollaboratorCommissionEntry.Status.PAID,
            "Month 7 commission should stay PAID when unpaying month 6 payroll",
        )
        self.assertIsNotNone(m7_entry.paid_at)

    def test_mark_payroll_as_paid_creates_missing_financial_movement(self) -> None:
        workshop = create_workshop(suffix=6)
        collaborator = create_collaborator(workshop=workshop, suffix=6)
        workorder = create_workorder(workshop=workshop, budget_type="sale")
        workorder.collaborators.add(collaborator)
        workorder.criado_em = timezone.make_aware(datetime(2026, 8, 2, 10, 0, 0))
        workorder.save(update_fields=["criado_em"])

        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )
        commission_entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=workorder,
            payroll=payroll,
            reference_year=2026,
            reference_month=8,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )

        refreshed_payroll = _mark_payroll_as_paid(payroll=payroll)
        refreshed_payroll.refresh_from_db()
        commission_entry.refresh_from_db()

        self.assertIsNotNone(refreshed_payroll.financial_movement)
        self.assertTrue(refreshed_payroll.financial_movement.is_paid)
        self.assertEqual(commission_entry.status, CollaboratorCommissionEntry.Status.PAID)
        self.assertIsNotNone(commission_entry.paid_at)


class CommissionAndPayrollCommandTests(TestCase):
    def test_cleanup_invalid_commission_entries_dry_run_and_apply(self) -> None:
        workshop = create_workshop(suffix=7)
        collaborator = create_collaborator(workshop=workshop, suffix=7)
        warranty_workorder = create_workorder(workshop=workshop, budget_type="warranty")
        warranty_workorder.collaborators.add(collaborator)
        entry = CollaboratorCommissionEntry.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            workorder=warranty_workorder,
            reference_year=2026,
            reference_month=1,
            percentage=Decimal("0.100000"),
            base_amount=Money(1000, "BRL"),
            commission_amount=Money(100, "BRL"),
            status=CollaboratorCommissionEntry.Status.FORECAST,
        )

        stdout = StringIO()
        call_command("cleanup_invalid_commission_entries", "--dry-run", "--entry-id", str(entry.pk), stdout=stdout)
        self.assertIn("Total encontrado: 1", stdout.getvalue())
        self.assertTrue(CollaboratorCommissionEntry.objects.filter(pk=entry.pk).exists())

        stdout = StringIO()
        call_command("cleanup_invalid_commission_entries", "--entry-id", str(entry.pk), stdout=stdout)
        self.assertIn("1 comissao(oes) invalida(s) removida(s).", stdout.getvalue())
        self.assertFalse(CollaboratorCommissionEntry.objects.filter(pk=entry.pk).exists())

    def test_backfill_payroll_financial_movements_dry_run_and_apply(self) -> None:
        workshop = create_workshop(suffix=8)
        collaborator = create_collaborator(workshop=workshop, suffix=8)
        payroll = CollaboratorPayroll.objects.create(
            workshop=workshop,
            collaborator=collaborator,
            reference_year=2026,
            reference_month=8,
            due_date=date(2026, 8, 5),
            salary_amount=Money(2000, "BRL"),
            total_amount=Money(2000, "BRL"),
        )

        stdout = StringIO()
        call_command("backfill_payroll_financial_movements", "--dry-run", "--payroll-id", str(payroll.pk), stdout=stdout)
        self.assertIn("Total encontrado: 1", stdout.getvalue())
        payroll.refresh_from_db()
        self.assertIsNone(payroll.financial_movement)

        stdout = StringIO()
        call_command("backfill_payroll_financial_movements", "--payroll-id", str(payroll.pk), stdout=stdout)
        self.assertIn("1 movimentacao(oes) financeira(s) criada(s).", stdout.getvalue())
        payroll.refresh_from_db()
        self.assertIsNotNone(payroll.financial_movement)
