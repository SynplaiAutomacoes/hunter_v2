from __future__ import annotations

from unittest.mock import Mock

from django.test import SimpleTestCase

from apps.customer.services.vehicle_km import sync_vehicle_km_from_exit


class VehicleKmSyncTests(SimpleTestCase):
    def test_initializes_empty_vehicle_odometer(self) -> None:
        vehicle = Mock(km=None)

        updated = sync_vehicle_km_from_exit(vehicle=vehicle, km_final=50_000)

        self.assertTrue(updated)
        self.assertEqual(vehicle.km, 50_000)
        vehicle.save.assert_called_once_with(update_fields=["km"])

    def test_updates_vehicle_odometer_when_exit_reading_is_higher(self) -> None:
        vehicle = Mock(km=50_000)

        updated = sync_vehicle_km_from_exit(vehicle=vehicle, km_final=50_500)

        self.assertTrue(updated)
        self.assertEqual(vehicle.km, 50_500)
        vehicle.save.assert_called_once_with(update_fields=["km"])

    def test_does_not_decrease_vehicle_odometer(self) -> None:
        vehicle = Mock(km=50_000)

        updated = sync_vehicle_km_from_exit(vehicle=vehicle, km_final=49_000)

        self.assertFalse(updated)
        self.assertEqual(vehicle.km, 50_000)
        vehicle.save.assert_not_called()

    def test_does_not_save_when_exit_reading_is_missing_or_unchanged(self) -> None:
        vehicle = Mock(km=50_000)

        missing_updated = sync_vehicle_km_from_exit(vehicle=vehicle, km_final=None)
        unchanged_updated = sync_vehicle_km_from_exit(vehicle=vehicle, km_final=50_000)

        self.assertFalse(missing_updated)
        self.assertFalse(unchanged_updated)
        vehicle.save.assert_not_called()
