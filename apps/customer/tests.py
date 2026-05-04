from __future__ import annotations

from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.budget.models import Budget
from apps.customer.forms import QuickVehicleForm
from apps.customer.models import Customer, Vehicle
from apps.workorder.models import WorkOrder
from apps.workshops.models.workshops import Workshop
from apps.workshops.tests import create_director_user_with_workshop


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

    def test_quick_vehicle_form_rejects_invalid_fuel_choice(self) -> None:
        form = QuickVehicleForm(
            data={
                "plate": "ABC1D23",
                "brand": "Jeep",
                "model": "Renegade",
                "engine": "2.0",
                "fuel": "Gas natural",
                "year_fabrication": "2020",
                "year_model": "2020",
                "color": "Prata",
            },
            workshop=self.workshop,
            customer=self.customer,
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["fuel"], ["Selecione um combustível válido."])

    def test_quick_vehicle_form_rejects_invalid_engine_choice(self) -> None:
        form = QuickVehicleForm(
            data={
                "plate": "ABC1D23",
                "brand": "Jeep",
                "model": "Renegade",
                "engine": "2.8",
                "fuel": "Diesel",
                "year_fabrication": "2020",
                "year_model": "2020",
                "color": "Prata",
            },
            workshop=self.workshop,
            customer=self.customer,
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["engine"], ["Selecione um motor válido."])

    def test_quick_vehicle_form_shows_blank_engine_for_unsupported_existing_value(self) -> None:
        vehicle = Vehicle.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            plate="ABC1D23",
            brand="Jeep",
            model="Renegade",
            engine="2.8",
            fuel="Diesel",
            year_fabrication="2020",
            year_model="2020",
            color="Prata",
        )

        form = QuickVehicleForm(instance=vehicle, workshop=self.workshop, customer=self.customer)

        self.assertEqual(form.initial["engine"], "")


class CustomerUpdateViewTabsTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=61)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Principal",
            cpf_or_cnpj="12345678901",
            email="cliente.principal@example.com",
            phone="+5511999999999",
            logradouro="Rua A",
            numero="100",
            bairro="Centro",
            cidade="Sao Paulo",
            estado="SP",
        )
        self.other_customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Secundario",
            cpf_or_cnpj="98765432100",
            email="cliente.secundario@example.com",
            phone="+5511888888888",
        )

        self.customer_vehicle = Vehicle.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            plate="ABC1D23",
            brand="Ford",
            model="Ka",
            year_fabrication="2021",
            year_model="2022",
            color="Prata",
        )
        Vehicle.objects.create(
            workshop=self.workshop,
            customer=self.other_customer,
            plate="XYZ9Z99",
            brand="Fiat",
            model="Uno",
            year_fabrication="2018",
            year_model="2019",
            color="Branco",
        )

        self.budget_without_os = Budget.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.customer_vehicle,
            entry_date=date(2026, 4, 10),
        )
        budget_with_os = Budget.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.customer_vehicle,
            entry_date=date(2026, 4, 12),
        )
        self.workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=budget_with_os,
        )

        other_vehicle = Vehicle.objects.get(customer=self.other_customer)
        other_budget = Budget.objects.create(
            workshop=self.workshop,
            customer=self.other_customer,
            vehicle=other_vehicle,
            entry_date=date(2026, 4, 14),
        )
        self.other_workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=other_budget,
        )

    def test_customer_update_page_shows_customer_info_and_history_tabs(self) -> None:
        response = self.client.get(reverse("customer:customer_update", kwargs={"pk": self.customer.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Informações do Cliente")
        self.assertContains(response, "Histórico do Cliente")
        self.assertContains(response, "Tipo")
        self.assertContains(response, "Número")
        self.assertContains(response, "Ações")
        self.assertNotContains(response, "Histórico de Clientes")
        self.assertNotContains(response, "Dados do Cliente")

    def test_customer_update_history_tab_shows_budget_and_workorder_rows(self) -> None:
        response = self.client.get(reverse("customer:customer_update", kwargs={"pk": self.customer.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.customer_vehicle.plate)
        self.assertContains(response, f"Orçamento #{self.budget_without_os.pk}")
        self.assertContains(response, f"OS #{self.workorder.pk}")
        self.assertContains(response, "open-pdf-modal")
        self.assertContains(response, "downloadUrl")

    def test_customer_update_history_tab_hides_budget_row_when_it_has_workorder(self) -> None:
        response = self.client.get(reverse("customer:customer_update", kwargs={"pk": self.customer.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f"Orçamento #{self.workorder.budget.pk}")
        self.assertContains(response, f"OS #{self.workorder.pk}")

    def test_customer_update_history_tab_context_is_scoped_to_current_customer(self) -> None:
        response = self.client.get(reverse("customer:customer_update", kwargs={"pk": self.customer.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.customer_vehicle.plate)
        self.assertNotContains(response, "XYZ9Z99")
        self.assertNotContains(response, f"OS #{self.other_workorder.pk}")
