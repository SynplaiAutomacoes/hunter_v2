from __future__ import annotations

from datetime import date
from unittest.mock import Mock, patch

from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from apps.budget.models import Budget
from apps.customer.fipe_service import get_fuel_options_for_model, register_catalog_access_and_maybe_sync
from apps.customer.forms import QuickVehicleForm
from apps.customer.models import Customer, FipeModelFuelCache, FipeSyncState, FipeVehicleBrand, FipeVehicleModel, Vehicle
from apps.customer.util import fetch_vehicle_data
from apps.customer.vehicle_engine import normalize_vehicle_engine_choice
from apps.customer.vehicle_fuel import normalize_vehicle_fuel_choice
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

    def test_quick_vehicle_form_accepts_engine_14(self) -> None:
        form = QuickVehicleForm(
            data={
                "plate": "ABC1D23",
                "brand": "Fiat",
                "model": "Uno",
                "engine": "1.4",
                "fuel": "Flex",
                "year_fabrication": "2020",
                "year_model": "2020",
                "color": "Prata",
            },
            workshop=self.workshop,
            customer=self.customer,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        vehicle = form.save()
        self.assertEqual(vehicle.engine, "1.4")

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

    def test_quick_vehicle_form_loads_brand_and_model_choices_from_fipe_catalog(self) -> None:
        FipeVehicleBrand.objects.create(name="Jeep", external_id="1")
        brand = FipeVehicleBrand.objects.get(name="Jeep")
        FipeVehicleModel.objects.create(brand=brand, vehicle_type=brand.vehicle_type, name="Renegade", external_id="10")

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

        brand_choices = [choice[0] for choice in form.fields["brand"].widget.choices]
        model_choices = [choice[0] for choice in form.fields["model"].widget.choices]

        self.assertIn("Jeep", brand_choices)
        self.assertIn("Renegade", model_choices)


class FipeCatalogServiceTests(TestCase):
    @override_settings(FIPE_SYNC_EVERY_ACCESS=False, FIPE_SYNC_ACCESS_INTERVAL=2)
    @patch("apps.customer.fipe_service.sync_all_brands_and_models")
    def test_register_catalog_access_triggers_sync_on_interval(self, sync_mock: Mock) -> None:
        FipeVehicleBrand.objects.create(name="Ford", external_id="22")

        register_catalog_access_and_maybe_sync()
        sync_mock.assert_not_called()

        register_catalog_access_and_maybe_sync()

        sync_mock.assert_called_once_with(vehicle_type="carros")
        state = FipeSyncState.objects.get(scope="vehicle_catalog")
        self.assertEqual(state.access_count, 2)
        self.assertFalse(state.sync_in_progress)

    @patch("apps.customer.fipe_service.requests.get")
    def test_get_fuel_options_for_model_populates_and_reuses_cache(self, requests_get_mock: Mock) -> None:
        brand = FipeVehicleBrand.objects.create(name="Ford", external_id="22")
        model = FipeVehicleModel.objects.create(brand=brand, vehicle_type=brand.vehicle_type, name="Ka", external_id="664")

        response_mock = Mock()
        response_mock.json.return_value = [
            {"id_modelo_ano": "1986-1", "name": "1986 Gasolina"},
            {"id_modelo_ano": "1987-5", "name": "1987 Flex"},
            {"id_modelo_ano": "1988-5", "name": "1988 Flex"},
        ]
        requests_get_mock.return_value = response_mock

        with patch.dict("os.environ", {"token_vehicle_api": "token-teste"}):
            fuel_values = get_fuel_options_for_model(brand_name="Ford", model_name="Ka")

        self.assertEqual(fuel_values, ["Gasolina", "Flex"])
        cache = FipeModelFuelCache.objects.get(model=model)
        self.assertEqual(cache.fuel_values, ["Gasolina", "Flex"])

        requests_get_mock.reset_mock()
        with patch.dict("os.environ", {"token_vehicle_api": "token-teste"}):
            cached_values = get_fuel_options_for_model(brand_name="Ford", model_name="Ka")

        self.assertEqual(cached_values, ["Gasolina", "Flex"])
        requests_get_mock.assert_not_called()


class CustomerFipeApiTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=71)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.brand = FipeVehicleBrand.objects.create(name="Ford", external_id="22")
        self.model = FipeVehicleModel.objects.create(brand=self.brand, vehicle_type=self.brand.vehicle_type, name="Ka", external_id="664")
        FipeModelFuelCache.objects.create(model=self.model, vehicle_type=self.model.vehicle_type, fuel_values=["Gasolina", "Flex"])

    def test_fipe_models_endpoint_returns_local_models(self) -> None:
        response = self.client.get(reverse("customer:fipe-models"), {"brand": "Ford"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{"id": "Ka", "label": "Ka"}])

    def test_fipe_fuels_endpoint_returns_cached_fuels(self) -> None:
        response = self.client.get(reverse("customer:fipe-fuels"), {"brand": "Ford", "model": "Ka"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{"id": "Gasolina", "label": "Gasolina"}, {"id": "Flex", "label": "Flex"}])


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


class VehicleLookupNormalizationTests(TestCase):
    def test_engine_normalization_maps_supported_text_and_displacement_values(self) -> None:
        self.assertEqual(normalize_vehicle_engine_choice("1.4"), "1.4")
        self.assertEqual(normalize_vehicle_engine_choice("Motor 1,4"), "1.4")
        self.assertEqual(normalize_vehicle_engine_choice("1368"), "1.3")
        self.assertEqual(normalize_vehicle_engine_choice("1398"), "1.3")
        self.assertEqual(normalize_vehicle_engine_choice("1400"), "1.4")
        self.assertEqual(normalize_vehicle_engine_choice("1798"), "1.8")
        self.assertEqual(normalize_vehicle_engine_choice("1998"), "2.0")

    def test_fuel_normalization_maps_alcool_gasolina_to_flex(self) -> None:
        self.assertEqual(normalize_vehicle_fuel_choice("Alcool / Gasolina"), "Flex")
        self.assertEqual(normalize_vehicle_fuel_choice("Flex"), "Flex")

    @patch.dict("os.environ", {"token_vehicle_api": "token-teste"})
    @patch("apps.customer.util.requests.get")
    def test_fetch_vehicle_data_parses_new_api_payload(self, requests_get_mock: Mock) -> None:
        response_mock = Mock()
        response_mock.json.return_value = {
            "data": {
                "veiculo": {
                    "ano": "2013/2013",
                    "cor": "Prata",
                    "chassi": "CHASSI",
                    "cilindradas": "1998",
                    "combustivel": "Alcool / Gasolina",
                    "marca_modelo": "Renault/duster D 4x4",
                    "tipo_de_veiculo": "Camioneta",
                },
                "fipes": [
                    {
                        "marca": "Renault",
                        "modelo": "DUSTER Dynamique 4x4 2.0 Hi-Flex 16V Mec",
                    }
                ],
            }
        }
        requests_get_mock.return_value = response_mock

        vehicle_data = fetch_vehicle_data("ABC1D23")

        self.assertEqual(
            vehicle_data,
            {
                "brand": "Renault",
                "model": "DUSTER Dynamique 4x4 2.0 Hi-Flex 16V Mec",
                "year_model": "2013",
                "year_fabrication": "2013",
                "color": "Prata",
                "chassi": "CHASSI",
                "renavam": None,
                "fuel": "Flex",
                "engine": "2.0",
                "type": "Camioneta",
            },
        )

    @patch.dict("os.environ", {"token_vehicle_api": "token-teste"})
    @patch("apps.customer.util.requests.get")
    def test_fetch_vehicle_data_parses_flat_data_payload(self, requests_get_mock: Mock) -> None:
        response_mock = Mock()
        response_mock.json.return_value = {
            "data": {
                "ano": "2018/2019",
                "cor": "Branca",
                "chassi": "CHASSI-FLAT",
                "renavam": "12345678901",
                "marca": "Volkswagen",
                "modelo": "Gol",
            },
            "extra": {
                "cilindradas": "1998",
                "combustivel": "Gasolina / Alcool",
                "tipo_veiculo": "Automovel",
            },
        }
        requests_get_mock.return_value = response_mock

        vehicle_data = fetch_vehicle_data("ABC1D23")

        self.assertEqual(
            vehicle_data,
            {
                "brand": "Volkswagen",
                "model": "Gol",
                "year_model": "2019",
                "year_fabrication": "2018",
                "color": "Branca",
                "chassi": "CHASSI-FLAT",
                "renavam": "12345678901",
                "fuel": "Flex",
                "engine": "2.0",
                "type": "Automovel",
            },
        )
