from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import PropertyMock, patch

from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetStatus
from apps.collaborators.models import CollaboratorCommissionEntry, WorkshopCollaborator
from apps.collaborators.services import sync_workorder_collaborator_payrolls
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
