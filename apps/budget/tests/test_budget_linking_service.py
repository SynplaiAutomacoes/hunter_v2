from datetime import date

from django.test import TestCase

from apps.budget.models import Budget, BudgetStatus
from apps.budget.services.budget_linking_service import find_oldest_open_budget_for_vehicle
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def create_workshop(suffix=1):
    return Workshop.objects.create(
        name=f"Oficina {suffix}",
        cnpj=f"81.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
        uf="SP",
    )


def create_vehicle(workshop, suffix=1, customer=None):
    from apps.customer.models import Customer, Vehicle
    if customer is None:
        customer = Customer.objects.create(
            workshop=workshop,
            name=f"Cliente {suffix}",
            phone="+5511988888888",
        )
    return Vehicle.objects.create(
        workshop=workshop,
        customer=customer,
        plate=f"ABC-{suffix:04d}",
        brand="Marca",
        model="Modelo",
        fuel="Gasolina",
    )


class FindOldestOpenBudgetForVehicleTests(TestCase):
    def setUp(self):
        self.workshop = create_workshop(1)
        self.customer = self.workshop.customer_set.create(
            name="Cliente Teste",
            phone="+5511988888888",
        )
        self.vehicle = create_vehicle(self.workshop, 1, self.customer)

    def _create_budget(self, status=BudgetStatus.DRAFT, vehicle=None):
        if vehicle is None:
            vehicle = self.vehicle
        return Budget.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=vehicle,
            status=status,
            entry_date=date.today(),
        )

    def _create_workorder(self, budget, status=WorkOrderStatus.DRAFT):
        return WorkOrder.objects.create(
            workshop=self.workshop,
            budget=budget,
            status=status,
        )

    def test_returns_none_when_no_budget_or_workorder(self):
        result = find_oldest_open_budget_for_vehicle(
            workshop_id=self.workshop.pk,
            vehicle_id=self.vehicle.pk,
        )
        self.assertIsNone(result)

    def test_returns_budget_when_non_terminal_exists(self):
        budget = self._create_budget(status=BudgetStatus.WAITING_CLIENT)
        result = find_oldest_open_budget_for_vehicle(
            workshop_id=self.workshop.pk,
            vehicle_id=self.vehicle.pk,
        )
        self.assertEqual(result.pk, budget.pk)

    def test_returns_oldest_when_multiple_non_terminal(self):
        older = self._create_budget(status=BudgetStatus.DRAFT)
        self._create_budget(status=BudgetStatus.WAITING_CLIENT)
        result = find_oldest_open_budget_for_vehicle(
            workshop_id=self.workshop.pk,
            vehicle_id=self.vehicle.pk,
        )
        self.assertEqual(result.pk, older.pk)

    def test_ignores_terminal_statuses(self):
        self._create_budget(status=BudgetStatus.APPROVED)
        self._create_budget(status=BudgetStatus.REJECTED)
        self._create_budget(status=BudgetStatus.CANCELLED)
        result = find_oldest_open_budget_for_vehicle(
            workshop_id=self.workshop.pk,
            vehicle_id=self.vehicle.pk,
        )
        self.assertIsNone(result)

    def test_returns_budget_when_workorder_active(self):
        approved_budget = self._create_budget(status=BudgetStatus.APPROVED)
        self._create_workorder(approved_budget, status=WorkOrderStatus.DRAFT)
        result = find_oldest_open_budget_for_vehicle(
            workshop_id=self.workshop.pk,
            vehicle_id=self.vehicle.pk,
        )
        self.assertEqual(result.pk, approved_budget.pk)

    def test_ignores_workorder_with_non_draft_status(self):
        approved_budget = self._create_budget(status=BudgetStatus.APPROVED)
        self._create_workorder(approved_budget, status=WorkOrderStatus.APPROVED)
        result = find_oldest_open_budget_for_vehicle(
            workshop_id=self.workshop.pk,
            vehicle_id=self.vehicle.pk,
        )
        self.assertIsNone(result)

    def test_prefers_oldest_non_terminal_over_workorder(self):
        old_non_terminal = self._create_budget(status=BudgetStatus.DRAFT)
        newer_with_workorder = self._create_budget(status=BudgetStatus.APPROVED)
        self._create_workorder(newer_with_workorder, status=WorkOrderStatus.DRAFT)
        result = find_oldest_open_budget_for_vehicle(
            workshop_id=self.workshop.pk,
            vehicle_id=self.vehicle.pk,
        )
        self.assertEqual(result.pk, old_non_terminal.pk)

    def test_different_vehicle_not_returned(self):
        other_vehicle = create_vehicle(self.workshop, 2)
        self._create_budget(vehicle=other_vehicle, status=BudgetStatus.DRAFT)
        result = find_oldest_open_budget_for_vehicle(
            workshop_id=self.workshop.pk,
            vehicle_id=self.vehicle.pk,
        )
        self.assertIsNone(result)

    def test_different_workshop_not_returned(self):
        other_workshop = create_workshop(2)
        budget = self._create_budget(status=BudgetStatus.DRAFT)
        budget.workshop = other_workshop
        budget.save(update_fields=["workshop"])
        result = find_oldest_open_budget_for_vehicle(
            workshop_id=self.workshop.pk,
            vehicle_id=self.vehicle.pk,
        )
        self.assertIsNone(result)

    def test_all_non_terminal_statuses(self):
        for status in BudgetStatus.values:
            if status in (BudgetStatus.APPROVED, BudgetStatus.REJECTED, BudgetStatus.CANCELLED):
                continue
            self._create_budget(status=status)
        result = find_oldest_open_budget_for_vehicle(
            workshop_id=self.workshop.pk,
            vehicle_id=self.vehicle.pk,
        )
        self.assertIsNotNone(result)
