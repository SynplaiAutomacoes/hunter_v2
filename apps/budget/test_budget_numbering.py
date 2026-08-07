from __future__ import annotations

from datetime import date

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.budget.models import Budget, WorkshopBudgetSequence
from apps.budget.services.numbering import allocate_budget_number
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def _create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Numero {suffix}",
        cnpj=f"11.222.333/0001-{suffix:02d}",
        phone="+5511987654321",
        address=f"Rua Numero, {suffix}",
        uf="SP",
    )


def _create_budget(*, workshop: Workshop, number: int | None = None) -> Budget:
    budget = Budget(workshop=workshop, entry_date=date(2026, 8, 1))
    if number is not None:
        budget.number = number
    budget.save()
    return budget


class BudgetNumberingServiceTests(TestCase):
    def test_empty_workshop_starts_at_one(self) -> None:
        workshop = _create_workshop(suffix=1)

        first = _create_budget(workshop=workshop)
        second = _create_budget(workshop=workshop)

        self.assertEqual(first.number, 1)
        self.assertEqual(second.number, 2)
        sequence = WorkshopBudgetSequence.objects.get(workshop=workshop)
        self.assertEqual(sequence.last_number, 2)

    def test_late_workshop_with_high_backfilled_numbers_starts_new_at_one(self) -> None:
        workshop = _create_workshop(suffix=2)
        existing_100 = _create_budget(workshop=workshop, number=100)
        existing_200 = _create_budget(workshop=workshop, number=200)
        WorkshopBudgetSequence.objects.update_or_create(workshop=workshop, defaults={"last_number": 0})

        new_budget = _create_budget(workshop=workshop)

        existing_100.refresh_from_db()
        existing_200.refresh_from_db()
        self.assertEqual(existing_100.number, 100)
        self.assertEqual(existing_200.number, 200)
        self.assertEqual(new_budget.number, 1)

        another = _create_budget(workshop=workshop)
        self.assertEqual(another.number, 2)

    def test_workshop_with_number_one_continues_past_max(self) -> None:
        workshop = _create_workshop(suffix=3)
        first = _create_budget(workshop=workshop, number=1)
        high = _create_budget(workshop=workshop, number=670)
        WorkshopBudgetSequence.objects.update_or_create(workshop=workshop, defaults={"last_number": 670})

        next_budget = _create_budget(workshop=workshop)

        first.refresh_from_db()
        high.refresh_from_db()
        self.assertEqual(first.number, 1)
        self.assertEqual(high.number, 670)
        self.assertEqual(next_budget.number, 671)

    def test_allocate_skips_occupied_numbers(self) -> None:
        workshop = _create_workshop(suffix=4)
        _create_budget(workshop=workshop, number=1)
        WorkshopBudgetSequence.objects.update_or_create(workshop=workshop, defaults={"last_number": 0})

        allocated = allocate_budget_number(workshop_id=workshop.pk)

        self.assertEqual(allocated, 2)

    def test_two_workshops_can_share_same_number(self) -> None:
        workshop_a = _create_workshop(suffix=5)
        workshop_b = _create_workshop(suffix=6)

        budget_a = _create_budget(workshop=workshop_a)
        budget_b = _create_budget(workshop=workshop_b)

        self.assertEqual(budget_a.number, 1)
        self.assertEqual(budget_b.number, 1)

    def test_unique_constraint_per_workshop(self) -> None:
        workshop = _create_workshop(suffix=7)
        _create_budget(workshop=workshop, number=10)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _create_budget(workshop=workshop, number=10)

    def test_workorder_get_id_uses_budget_number(self) -> None:
        workshop = _create_workshop(suffix=8)
        budget = _create_budget(workshop=workshop, number=42)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.DRAFT)

        self.assertEqual(workorder.get_id, 42)
        self.assertEqual(workorder.public_number, 42)

    def test_existing_numbers_remain_intact_when_creating_new(self) -> None:
        workshop = _create_workshop(suffix=9)
        historical = _create_budget(workshop=workshop, number=150)
        WorkshopBudgetSequence.objects.update_or_create(workshop=workshop, defaults={"last_number": 0})

        fresh = _create_budget(workshop=workshop)

        historical.refresh_from_db()
        self.assertEqual(historical.number, 150)
        self.assertEqual(fresh.number, 1)
        self.assertNotEqual(historical.pk, fresh.pk)
