from __future__ import annotations

from django.test import TestCase

from apps.customer.forms import QuickVehicleForm
from apps.customer.models import Customer, Vehicle
from apps.workshops.models.workshops import Workshop


class QuickVehicleFormTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(name="Oficina Cliente", phone="+5511999999999", address="Rua Cliente, 10")
        self.customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Veiculo",
            cpf_or_cnpj="123.456.789-01",
            email="cliente.veiculo@example.com",
            phone="+5511999999999",
        )

    def test_quick_vehicle_form_persists_engine_and_fuel(self) -> None:
        form = QuickVehicleForm(
            data={
                "plate": "ABC1D23",
                "brand": "Jeep",
                "model": "Renegade",
                "engine": "2.0",
                "fuel": "Diesel",
                "year_fabrication": "2020",
                "year_model": "2020",
                "color": "Prata",
            },
            workshop=self.workshop,
            customer=self.customer,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        vehicle = form.save()

        self.assertIsInstance(vehicle, Vehicle)
        self.assertEqual(vehicle.engine, "2.0")
        self.assertEqual(vehicle.fuel, "Diesel")
