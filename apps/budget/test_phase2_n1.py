from __future__ import annotations

from datetime import date

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem
from apps.collaborators.models import WorkshopCollaborator
from apps.collaborators.services import _is_workorder_commission_paid
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.views.financial_movement import _apply_paid_status_filter_to_queryset
from apps.workorder.models import WorkOrder
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Fase2 {suffix}",
        cnpj=f"45.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Fase2, 123",
    )


class CollaboratorNamePrefetchTests(TestCase):
    def test_collaborator_name_uses_prefetched_list_without_exists_query(self) -> None:
        workshop = create_workshop(suffix=1)
        budget = Budget.objects.create(workshop=workshop, entry_date=date(2026, 7, 1))
        collaborator = WorkshopCollaborator.objects.create(
            workshop=workshop,
            name="Joao Prefetch",
            cpf="12345678901",
            birth_date=date(1990, 1, 1),
            salary=Money(2000, "BRL"),
            admission_date=date(2025, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
        )
        budget.collaborators.add(collaborator)

        budget = Budget.objects.prefetch_related("collaborators").get(pk=budget.pk)
        with CaptureQueriesContext(connection) as ctx:
            name = budget.collaborator_name

        self.assertEqual(name, "Joao Prefetch")
        self.assertEqual(len(ctx), 0)


class CommissionPaidPrefetchTests(TestCase):
    def test_is_workorder_commission_paid_uses_prefetched_movements(self) -> None:
        workshop = create_workshop(suffix=2)
        budget = Budget.objects.create(workshop=workshop, entry_date=date(2026, 7, 2))
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        FinancialMovement.objects.create(
            workshop=workshop,
            workorder=workorder,
            direction=FinancialMovement.MovementDirection.CREDIT,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            description="OS pai",
            amount=Money(100, "BRL"),
            due_date=date(2026, 7, 15),
            is_paid=True,
        )

        workorder = WorkOrder.objects.filter(pk=workorder.pk).prefetch_related("financial_movements").get()
        with CaptureQueriesContext(connection) as ctx:
            paid = _is_workorder_commission_paid(workorder=workorder)

        self.assertTrue(paid)
        self.assertEqual(len(ctx), 0)


class PaidStatusFilterOrmTests(TestCase):
    def test_paid_status_filter_uses_is_paid_lookup(self) -> None:
        filtered = _apply_paid_status_filter_to_queryset(FinancialMovement.objects.filter(pk__gte=0), paid_status="paid")
        self.assertIn("is_paid", str(filtered.query))


class WarrantyItemsCountPrefetchTests(TestCase):
    def test_warranty_count_uses_prefetched_items(self) -> None:
        workshop = create_workshop(suffix=3)
        budget = Budget.objects.create(workshop=workshop, entry_date=date(2026, 7, 3))
        warranty_item = BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            description="Item garantia",
            quantity=1,
            is_local=True,
        )
        BudgetItem.objects.filter(pk=warranty_item.pk).update(item_benefit_type="warranty")
        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            description="Item normal",
            quantity=1,
            is_local=True,
        )

        budget = Budget.objects.prefetch_related("items").get(pk=budget.pk)
        with CaptureQueriesContext(connection) as ctx:
            count = budget.warranty_items_count

        self.assertEqual(count, 1)
        self.assertEqual(len(ctx), 0)
