from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem, BudgetStatus
from apps.catalog.models.kits import Kit, KitService
from apps.catalog.models.services import Service
from apps.collaborators.models import WorkshopCollaborator
from apps.workorder.models import WorkOrder
from apps.workshops.models.workshops import Workshop


class WorkOrderCollaboratorIndependenceTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Colaboradores OS",
            cnpj="12.345.678/0001-90",
            phone="+5511999999997",
            address="Rua Colaboradores, 1",
        )
        self.collaborator = WorkshopCollaborator.objects.create(
            workshop=self.workshop,
            name="Mecânico Orçamento",
            cpf="12345678901",
            birth_date=date(1990, 1, 1),
            salary=Money(2000, "BRL"),
            admission_date=date(2025, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
            receives_commission=True,
            commission_percentage=Decimal("0.100000"),
        )

    def test_approved_budget_creates_workorder_without_budget_collaborators(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 8, 1),
            status=BudgetStatus.WAITING_APPROVAL,
        )
        budget.collaborators.add(self.collaborator)
        budget.collaborator = self.collaborator
        budget.save(update_fields=["collaborator"])

        budget.status = BudgetStatus.APPROVED
        budget.save(update_fields=["status"])

        workorder = WorkOrder.objects.get(budget=budget)
        self.assertEqual(workorder.collaborators.count(), 0)

    def test_sync_from_budget_does_not_copy_budget_collaborators(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            entry_date=date(2026, 8, 1),
            status=BudgetStatus.APPROVED,
        )
        budget.collaborators.add(self.collaborator)
        budget.collaborator = self.collaborator
        budget.save(update_fields=["collaborator"])

        workorder = WorkOrder.objects.get(budget=budget)
        workorder.sync_from_budget()

        self.assertEqual(workorder.collaborators.count(), 0)

    def test_sync_from_budget_preserves_kit_component_exclusion(self) -> None:
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço mantido no valor do kit",
            duration=timedelta(minutes=10),
            suggested_cost=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
        )
        kit = Kit.objects.create(workshop=self.workshop, name="Kit com serviço excluído")
        KitService.objects.create(kit=kit, service=service, quantity=1, duration=timedelta(minutes=10))
        budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 8, 1))
        budget_item = BudgetItem.objects.create(workshop=self.workshop, budget=budget, kit=kit)
        budget_override = budget_item.kit_overrides.get(service=service)
        budget_override.excluded_from_composition = True
        budget_override.save(update_fields=["excluded_from_composition"])

        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget)
        workorder.sync_from_budget()

        workorder_override = workorder.items.get(kit=kit).kit_overrides.get(service=service)
        self.assertTrue(workorder_override.excluded_from_composition)
