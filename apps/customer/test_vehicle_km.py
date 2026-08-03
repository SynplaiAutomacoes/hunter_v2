from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.budget.approval import approve_budget_with_stock
from apps.budget.models import Budget, BudgetStatus
from apps.customer.models import Customer, Vehicle
from apps.customer.services.vehicle_km import sync_vehicle_km_from_exit
from apps.workorder.models import WorkOrder
from apps.workshops.models.workshops import Workshop


User = get_user_model()


class VehicleKmSyncTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina KM",
            cnpj="12.345.678/0001-90",
            phone="+5511999999999",
            address="Rua KM, 1",
            uf="SP",
        )
        self.customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente KM",
            cpf_or_cnpj="52998224725",
            email="km@example.invalid",
        )
        self.vehicle = Vehicle.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            plate="KMZ1A23",
            brand="Marca",
            model="Modelo",
            year_fabrication="2020",
            year_model="2021",
            color="Preto",
            km=50_000,
        )

    def test_sync_vehicle_km_from_exit_updates_when_higher(self) -> None:
        updated = sync_vehicle_km_from_exit(vehicle=self.vehicle, km_final=50_500)
        self.vehicle.refresh_from_db()
        self.assertTrue(updated)
        self.assertEqual(self.vehicle.km, 50_500)

    def test_sync_vehicle_km_from_exit_does_not_decrease(self) -> None:
        updated = sync_vehicle_km_from_exit(vehicle=self.vehicle, km_final=49_000)
        self.vehicle.refresh_from_db()
        self.assertFalse(updated)
        self.assertEqual(self.vehicle.km, 50_000)

    def test_sync_vehicle_km_from_exit_initializes_empty_odometer(self) -> None:
        self.vehicle.km = None
        self.vehicle.save(update_fields=["km"])

        updated = sync_vehicle_km_from_exit(vehicle=self.vehicle, km_final=50_000)

        self.vehicle.refresh_from_db()
        self.assertTrue(updated)
        self.assertEqual(self.vehicle.km, 50_000)

    def test_sync_vehicle_km_from_exit_ignores_missing_or_unchanged_reading(self) -> None:
        self.assertFalse(sync_vehicle_km_from_exit(vehicle=self.vehicle, km_final=None))
        self.assertFalse(sync_vehicle_km_from_exit(vehicle=self.vehicle, km_final=50_000))
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.km, 50_000)

    def test_budget_approval_does_not_overwrite_vehicle_km_with_entry_km(self) -> None:
        user = User.objects.create_user(username="km-user", password="senha123", cpf="12345678901")
        budget = Budget.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.vehicle,
            entry_date=date(2026, 7, 8),
            status=BudgetStatus.DRAFT,
            current_km=45_000,
            current_step=6,
            service_expected_completion_at=timezone.now(),
            customer_agreed_departure_at=timezone.now() + timedelta(days=1),
        )

        with patch("apps.finance.services.workorder_financial_movements.sync_workorder_financial_movement"):
            approve_budget_with_stock(budget=budget, user=user)

        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.km, 50_000)

    def test_set_km_final_updates_vehicle_km(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.vehicle,
            entry_date=date(2026, 7, 8),
            status=BudgetStatus.APPROVED,
            current_km=50_000,
        )
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget)

        workorder.set_km_final(51_200)

        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.km, 51_200)
        self.assertEqual(workorder.km_final, 51_200)

    def test_complete_delivery_updates_vehicle_km(self) -> None:
        budget = Budget.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.vehicle,
            entry_date=date(2026, 7, 8),
            status=BudgetStatus.APPROVED,
            current_km=50_000,
        )
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget)

        workorder.complete_delivery(km_final=52_000)

        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.km, 52_000)
        self.assertEqual(workorder.km_final, 52_000)
