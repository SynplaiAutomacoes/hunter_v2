from __future__ import annotations

import datetime
import json
from decimal import Decimal
from unittest.mock import Mock, patch

from crispy_forms.utils import render_crispy_form
from django.db import IntegrityError
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from djmoney.money import Money

from apps.catalog.fipe_service import extract_fuel_from_model_name, get_fuel_options_for_model, register_catalog_access_and_maybe_sync
from apps.catalog.kit_applications import evaluate_kit_vehicle_compatibility
from apps.catalog.forms.kits import KitForm, QuickProductEditForm
from apps.catalog.forms.products import ProductForm
from apps.catalog.models import FipeModelFuelCache, FipeSyncState, FipeVehicleBrand, FipeVehicleModel
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit, KitApplication, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.catalog.util import recalculate_kit_totals
from apps.customer.models import Customer, Vehicle
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.tests import create_director_user_with_workshop
from apps.workshops.models.workshops import Workshop


class KitTests(TestCase):
    def setUp(self):
        self.workshop = Workshop.objects.create(name="Oficina Teste", phone="+5511999999999", address="Rua Teste, 123")

    @staticmethod
    def build_application_payload(*, brand: str = "Jeep", model: str = "Renegade", engine: str = "2.0", fuel: str = "Diesel", year_start: str = "2015", year_end: str = "2021") -> dict[str, list[str] | str]:
        return {
            "kit_application_brand": [brand],
            "kit_application_model": [model],
            "kit_application_engine": [engine],
            "kit_application_fuel": [fuel],
            "kit_application_year_start": [year_start],
            "kit_application_year_end": [year_end],
        }

    def test_unique_service_per_kit_constraint(self):
        kit = Kit.objects.create(workshop=self.workshop, name="Kit A", description="", is_active=True)
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=None,
            is_third_party=False,
            is_active=True,
        )

        KitService.objects.create(kit=kit, service=service)
        with self.assertRaises(IntegrityError):
            KitService.objects.create(kit=kit, service=service)

    def test_kit_form_rejects_duplicate_services(self):
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=None,
            is_third_party=False,
            is_active=True,
        )

        form = KitForm(
            data={
                "name": "Kit A",
                "description": "",
                "is_active": "on",
                "kit_services": [str(service.id), str(service.id)],
                **self.build_application_payload(),
            },
            workshop=self.workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Existem serviços repetidos no kit.", form.non_field_errors())

    def test_kit_form_rejects_duplicate_name_in_same_workshop(self):
        Kit.objects.create(workshop=self.workshop, name="Kit Revisao", description="", is_active=True)

        form = KitForm(
            data={
                "name": "Kit Revisao",
                "description": "",
                "is_active": "on",
                **self.build_application_payload(),
            },
            workshop=self.workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Já existe um kit com este nome na oficina ativa.", form.errors.get("name", []))

    def test_kit_form_persists_service_quantity(self):
        kit = Kit.objects.create(workshop=self.workshop, name="Kit A", description="", is_active=True)
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=None,
            is_third_party=False,
            is_active=True,
        )

        form = KitForm(
            instance=kit,
            data={
                "name": "Kit A",
                "description": "",
                "is_active": "on",
                "kit_services": [str(service.id)],
                f"kit_service_qty_{service.id}": "2",
                **self.build_application_payload(),
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.save()

        item = KitService.objects.get(kit=kit, service=service)
        self.assertEqual(item.quantity, 2)

    def test_kit_form_persists_service_duration(self):
        kit = Kit.objects.create(workshop=self.workshop, name="Kit A", description="", is_active=True)
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=None,
            is_third_party=False,
            is_active=True,
        )

        form = KitForm(
            instance=kit,
            data={
                "name": "Kit A",
                "description": "",
                "is_active": "on",
                "kit_services": [str(service.id)],
                f"kit_service_qty_{service.id}": "2",
                f"kit_service_duration_{service.id}": "01:20:00",
                **self.build_application_payload(),
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.save()

        item = KitService.objects.get(kit=kit, service=service)
        self.assertEqual(item.duration, datetime.timedelta(hours=1, minutes=20))

    def test_kit_form_updates_total_price_from_inserted_value_mode(self):
        kit = Kit.objects.create(workshop=self.workshop, name="Kit A", description="", is_active=True)
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=None,
            is_third_party=False,
            is_active=True,
        )

        form = KitForm(
            instance=kit,
            data={
                "name": "Kit A",
                "description": "",
                "is_active": "on",
                "kit_services": [str(service.id)],
                "kit_service_pricing_mode": Kit.ServicePricingMode.INSERTED_VALUE,
                f"kit_service_qty_{service.id}": "2",
                f"kit_service_sell_by_duration_{service.id}": "48.90",
                f"kit_service_sell_{service.id}": "32.50",
                **self.build_application_payload(),
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.save()

        item = KitService.objects.get(kit=kit, service=service)
        kit.refresh_from_db()

        self.assertEqual(item.selling_price, Money("32.50", "BRL"))
        self.assertEqual(kit.total_price, Money("65.00", "BRL"))

    def test_kit_form_updates_total_price_from_duration_value_mode(self):
        kit = Kit.objects.create(workshop=self.workshop, name="Kit Duracao Total", description="", is_active=True)
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=None,
            is_third_party=False,
            is_active=True,
        )

        form = KitForm(
            instance=kit,
            data={
                "name": "Kit Duracao Total",
                "description": "",
                "is_active": "on",
                "kit_services": [str(service.id)],
                "kit_service_pricing_mode": Kit.ServicePricingMode.BY_DURATION,
                f"kit_service_qty_{service.id}": "2",
                f"kit_service_sell_by_duration_{service.id}": "48.90",
                f"kit_service_sell_{service.id}": "32.50",
                **self.build_application_payload(),
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.save()

        item = KitService.objects.get(kit=kit, service=service)
        kit.refresh_from_db()

        self.assertEqual(item.duration_selling_price, Money("48.90", "BRL"))
        self.assertEqual(kit.total_price, Money("97.80", "BRL"))

    def test_kit_form_persists_local_service_cost(self):
        kit = Kit.objects.create(workshop=self.workshop, name="Kit Custo", description="", is_active=True)
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=Money(5, "BRL"),
            is_third_party=False,
            is_active=True,
        )

        form = KitForm(
            instance=kit,
            data={
                "name": "Kit Custo",
                "description": "",
                "is_active": "on",
                "kit_services": [str(service.id)],
                f"kit_service_qty_{service.id}": "2",
                f"kit_service_cost_{service.id}": "18.75",
                f"kit_service_sell_{service.id}": "32.50",
                **self.build_application_payload(),
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.save()

        item = KitService.objects.get(kit=kit, service=service)
        self.assertEqual(item.cost_price, Money("18.75", "BRL"))

    def test_kit_form_persists_local_service_duration_selling_price(self):
        kit = Kit.objects.create(workshop=self.workshop, name="Kit Duracao", description="", is_active=True)
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=Money(5, "BRL"),
            is_third_party=False,
            is_active=True,
        )

        form = KitForm(
            instance=kit,
            data={
                "name": "Kit Duracao",
                "description": "",
                "is_active": "on",
                "kit_services": [str(service.id)],
                f"kit_service_sell_by_duration_{service.id}": "48.90",
                f"kit_service_sell_{service.id}": "32.50",
                **self.build_application_payload(),
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.save()

        item = KitService.objects.get(kit=kit, service=service)
        self.assertEqual(item.duration_selling_price, Money("48.90", "BRL"))

    def test_kit_form_persists_selected_service_pricing_mode(self):
        kit = Kit.objects.create(workshop=self.workshop, name="Kit Modo", description="", is_active=True)
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=None,
            is_third_party=False,
            is_active=True,
        )

        form = KitForm(
            instance=kit,
            data={
                "name": "Kit Modo",
                "description": "",
                "is_active": "on",
                "kit_services": [str(service.id)],
                "kit_service_pricing_mode": Kit.ServicePricingMode.INSERTED_VALUE,
                **self.build_application_payload(),
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.save()
        kit.refresh_from_db()

        self.assertEqual(kit.service_pricing_mode, Kit.ServicePricingMode.INSERTED_VALUE)

    def test_kit_form_rejects_invalid_service_quantity(self):
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=None,
            is_third_party=False,
            is_active=True,
        )

        form = KitForm(
            data={
                "name": "Kit A",
                "description": "",
                "is_active": "on",
                "kit_services": [str(service.id)],
                f"kit_service_qty_{service.id}": "0",
                **self.build_application_payload(),
            },
            workshop=self.workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Quantidade inválida para serviço.", form.non_field_errors())

    def test_kit_form_rejects_invalid_service_duration(self):
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=None,
            is_third_party=False,
            is_active=True,
        )

        form = KitForm(
            data={
                "name": "Kit A",
                "description": "",
                "is_active": "on",
                "kit_services": [str(service.id)],
                f"kit_service_duration_{service.id}": "01:75:00",
                **self.build_application_payload(),
            },
            workshop=self.workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Duração inválida para serviço.", form.non_field_errors())

    def test_kit_form_rejects_invalid_service_selling_price(self):
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=None,
            is_third_party=False,
            is_active=True,
        )

        form = KitForm(
            data={
                "name": "Kit A",
                "description": "",
                "is_active": "on",
                "kit_services": [str(service.id)],
                f"kit_service_sell_{service.id}": "invalido",
                **self.build_application_payload(),
            },
            workshop=self.workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Valor de venda inválido para serviço.", form.non_field_errors())

    def test_kit_form_rejects_invalid_service_cost_price(self):
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=None,
            is_third_party=False,
            is_active=True,
        )

        form = KitForm(
            data={
                "name": "Kit A",
                "description": "",
                "is_active": "on",
                "kit_services": [str(service.id)],
                f"kit_service_cost_{service.id}": "invalido",
                **self.build_application_payload(),
            },
            workshop=self.workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Valor de custo inválido para serviço.", form.non_field_errors())

    def test_kit_form_rejects_invalid_service_duration_selling_price(self):
        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=None,
            is_third_party=False,
            is_active=True,
        )

        form = KitForm(
            data={
                "name": "Kit A",
                "description": "",
                "is_active": "on",
                "kit_services": [str(service.id)],
                f"kit_service_sell_by_duration_{service.id}": "invalido",
                **self.build_application_payload(),
            },
            workshop=self.workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Valor de venda por tempo inválido para serviço.", form.non_field_errors())

    def test_kit_form_allows_save_without_applications(self):
        form = KitForm(
            data={
                "name": "Kit Sem Aplicação",
                "description": "",
                "is_active": "on",
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.instance.workshop = self.workshop
        kit = form.save()

        self.assertEqual(KitApplication.objects.filter(kit=kit).count(), 0)
        self.assertEqual(kit.applications_summary, "Sem aplicação cadastrada")

    def test_kit_form_persists_multiple_applications(self):
        form = KitForm(
            data={
                "name": "Kit Correia",
                "description": "",
                "is_active": "on",
                "kit_application_brand": ["Jeep", "Fiat"],
                "kit_application_model": ["Renegade", "Toro"],
                "kit_application_engine": ["2.0", "2.0"],
                "kit_application_fuel": ["Diesel", "Diesel"],
                "kit_application_year_start": ["2015", "2015"],
                "kit_application_year_end": ["2021", "2021"],
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.instance.workshop = self.workshop
        kit = form.save()

        self.assertEqual(KitApplication.objects.filter(kit=kit).count(), 2)
        self.assertEqual(kit.applications_summary, "Jeep Renegade 2.0 Diesel 2015 a 2021; +1")

    def test_kit_form_normalizes_application_engine_and_fuel_choices(self):
        form = KitForm(
            data={
                "name": "Kit Flex",
                "description": "",
                "is_active": "on",
                **self.build_application_payload(engine="Motor 2,0 Turbo", fuel="gasolina e etanol"),
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.instance.workshop = self.workshop
        kit = form.save()

        application = KitApplication.objects.get(kit=kit)
        self.assertEqual(application.engine, "2.0")
        self.assertEqual(application.fuel, "Flex")

    def test_kit_form_accepts_dynamic_application_engine_choice(self):
        form = KitForm(
            data={
                "name": "Kit Motor Dinamico",
                "description": "",
                "is_active": "on",
                **self.build_application_payload(engine="2.8"),
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        form.instance.workshop = self.workshop
        kit = form.save()

        application = KitApplication.objects.get(kit=kit)
        self.assertEqual(application.engine, "2.8")

    def test_kit_form_rejects_invalid_application_fuel_choice(self):
        form = KitForm(
            data={
                "name": "Kit Combustivel Invalido",
                "description": "",
                "is_active": "on",
                **self.build_application_payload(fuel="GNV"),
            },
            workshop=self.workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Selecione um combustível válido em todas as aplicações do kit.", form.non_field_errors())

    def test_kit_form_preserves_dynamic_engine_and_blanks_unsupported_fuel_for_existing_application(self):
        kit = Kit.objects.create(workshop=self.workshop, name="Kit Legado", description="", is_active=True)
        KitApplication.objects.create(kit=kit, brand="Jeep", model="Renegade", engine="2.8", fuel="GNV", year_start=2020, year_end=2021)

        form = KitForm(instance=kit, workshop=self.workshop)

        self.assertEqual(
            form._build_initial_applications(),
            [
                {
                    "brand": "Jeep",
                    "model": "Renegade",
                    "engine": "2.8",
                    "fuel": "",
                    "year_start": "2020",
                    "year_end": "2021",
                }
            ],
        )

    def test_kit_form_rejects_invalid_application_year_range(self):
        form = KitForm(
            data={
                "name": "Kit Invalido",
                "description": "",
                "is_active": "on",
                "kit_application_brand": ["Jeep"],
                "kit_application_model": ["Compass"],
                "kit_application_engine": ["2.0"],
                "kit_application_fuel": ["Diesel"],
                "kit_application_year_start": ["2022"],
                "kit_application_year_end": ["2021"],
            },
            workshop=self.workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("O ano inicial da aplicação não pode ser maior que o ano final.", form.non_field_errors())

    def test_kit_form_renders_existing_fipe_brand_option(self):
        FipeVehicleBrand.objects.create(name="Jeep", external_id="1")

        form = KitForm(workshop=self.workshop)
        html = render_crispy_form(form)

        self.assertIn("brandOptions", html)
        self.assertIn("Jeep", html)


class CatalogFipeServiceTests(TestCase):
    @override_settings(FIPE_API_TOKEN="token-teste")
    @patch("apps.catalog.fipe_service._start_full_sync_in_background")
    def test_register_catalog_access_triggers_background_sync_only_when_catalog_is_empty(self, background_sync_mock: Mock) -> None:
        FipeVehicleBrand.objects.create(name="Ford", external_id="22")

        register_catalog_access_and_maybe_sync()
        background_sync_mock.assert_not_called()
        self.assertFalse(FipeSyncState.objects.filter(scope="kit_vehicle_catalog").exists())

    @override_settings(FIPE_API_TOKEN="token-teste")
    @patch("apps.catalog.fipe_service._start_full_sync_in_background")
    def test_register_catalog_access_bootstraps_once_for_empty_catalog(self, background_sync_mock: Mock) -> None:
        register_catalog_access_and_maybe_sync()

        background_sync_mock.assert_called_once_with(vehicle_type="carros")
        state = FipeSyncState.objects.get(scope="kit_vehicle_catalog")
        self.assertTrue(state.sync_in_progress)

    @override_settings(FIPE_DEV_MODE=True)
    @patch("apps.catalog.fipe_service._start_full_sync_in_background")
    def test_register_catalog_access_skips_full_sync_in_dev_mode(self, background_sync_mock: Mock) -> None:
        register_catalog_access_and_maybe_sync()

        background_sync_mock.assert_not_called()
        self.assertFalse(FipeSyncState.objects.filter(scope="kit_vehicle_catalog").exists())

    @override_settings(FIPE_API_TOKEN="token-teste", FIPE_DEV_MODE=True)
    @patch("apps.catalog.fipe_service.requests.get")
    def test_get_brand_options_syncs_only_brands_when_catalog_is_empty(self, requests_get_mock: Mock) -> None:
        response_mock = Mock()
        response_mock.json.return_value = [{"id": "22", "name": "Ford"}]
        requests_get_mock.return_value = response_mock

        from apps.catalog.fipe_service import get_brand_options

        brand_options = get_brand_options()

        self.assertEqual([option.value for option in brand_options], ["Ford"])
        requests_get_mock.assert_called_once()
        self.assertIn("/v1/carros?apikey=", requests_get_mock.call_args.args[0])

    @override_settings(FIPE_API_TOKEN="token-teste", FIPE_DEV_MODE=True)
    @patch("apps.catalog.fipe_service.requests.get")
    def test_get_model_options_syncs_only_selected_brand_when_models_are_missing(self, requests_get_mock: Mock) -> None:
        brand = FipeVehicleBrand.objects.create(name="Ford", external_id="22")

        response_mock = Mock()
        response_mock.json.return_value = [{"id_modelo": "664", "name": "Ka"}]
        requests_get_mock.return_value = response_mock

        from apps.catalog.fipe_service import get_model_options

        model_options = get_model_options(brand_name=brand.name)

        self.assertEqual([option.value for option in model_options], ["Ka"])
        requests_get_mock.assert_called_once()
        self.assertIn("/v1/carros/22?apikey=", requests_get_mock.call_args.args[0])

    @override_settings(FIPE_API_TOKEN="token-teste")
    @patch("apps.catalog.fipe_service.requests.get")
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

        fuel_values = get_fuel_options_for_model(brand_name="Ford", model_name="Ka")

        self.assertEqual(fuel_values, ["Gasolina", "Flex"])
        cache = FipeModelFuelCache.objects.get(model=model)
        self.assertEqual(cache.fuel_values, ["Gasolina", "Flex"])

        requests_get_mock.reset_mock()
        cached_values = get_fuel_options_for_model(brand_name="Ford", model_name="Ka")

        self.assertEqual(cached_values, ["Gasolina", "Flex"])
        requests_get_mock.assert_not_called()

    @override_settings(FIPE_API_TOKEN="token-teste")
    @patch("apps.catalog.fipe_service.requests.get")
    def test_get_fuel_options_for_model_prefers_inference_from_model_name(self, requests_get_mock: Mock) -> None:
        FipeVehicleBrand.objects.create(name="Ford", external_id="22")

        fuel_values = get_fuel_options_for_model(brand_name="Ford", model_name="Ka 1.0 Flex")

        self.assertEqual(fuel_values, ["Flex"])
        requests_get_mock.assert_not_called()

    def test_extract_fuel_from_model_name_detects_common_patterns(self) -> None:
        self.assertEqual(extract_fuel_from_model_name("DUSTER Dynamique 4x4 2.0 Hi-Flex 16V Mec"), "Flex")
        self.assertEqual(extract_fuel_from_model_name("Commander Overl. 2.2 TD 4x4 Diesel Aut"), "Diesel")
        self.assertEqual(extract_fuel_from_model_name("ZOE Intense (Eletrico)"), "Elétrico")
        self.assertEqual(extract_fuel_from_model_name("Accord Sedan 2.0 TB 16V Aut. (Hibrido)"), "Híbrido")
        self.assertEqual(extract_fuel_from_model_name("Civic Touring 1.5 Turbo"), "")

    @override_settings(FIPE_API_TOKEN="token-teste")
    @patch("apps.catalog.fipe_service.requests.get")
    def test_get_fuel_options_logs_normalization_warning_for_unknown_fuel(self, requests_get_mock: Mock) -> None:
        brand = FipeVehicleBrand.objects.create(name="Ford", external_id="22")
        FipeVehicleModel.objects.create(brand=brand, vehicle_type=brand.vehicle_type, name="Ka", external_id="664")

        response_mock = Mock()
        response_mock.json.return_value = [{"id_modelo_ano": "1986-99", "name": "1986 Combustivel X"}]
        requests_get_mock.return_value = response_mock

        with self.assertLogs("apps.catalog.fipe_service", level="WARNING") as captured_logs:
            fuel_values = get_fuel_options_for_model(brand_name="Ford", model_name="Ka", force_refresh=True)

        self.assertEqual(fuel_values, [])
        self.assertTrue(any("could not be normalized" in message for message in captured_logs.output))

    @override_settings(FIPE_API_TOKEN="token-teste")
    @patch("apps.catalog.fipe_service.requests.get")
    def test_get_fuel_options_logs_request_failure(self, requests_get_mock: Mock) -> None:
        brand = FipeVehicleBrand.objects.create(name="Ford", external_id="22")
        FipeVehicleModel.objects.create(brand=brand, vehicle_type=brand.vehicle_type, name="Ka", external_id="664")

        requests_get_mock.side_effect = RuntimeError("falha externa")

        with self.assertLogs("apps.catalog.fipe_service", level="ERROR") as captured_logs:
            with self.assertRaises(RuntimeError):
                get_fuel_options_for_model(brand_name="Ford", model_name="Ka", force_refresh=True)

        self.assertTrue(any("FIPE request failed" in message for message in captured_logs.output))

    @override_settings(FIPE_API_TOKEN="token-teste")
    @patch("apps.catalog.fipe_service.requests.get")
    def test_get_fuel_options_accepts_dict_payload_with_data_key(self, requests_get_mock: Mock) -> None:
        brand = FipeVehicleBrand.objects.create(name="Ford", external_id="22")
        FipeVehicleModel.objects.create(brand=brand, vehicle_type=brand.vehicle_type, name="Ka", external_id="664")

        response_mock = Mock()
        response_mock.json.return_value = {
            "data": [
                {"id_modelo_ano": "1986-1", "name": "1986 Gasolina"},
                {"id_modelo_ano": "1987-5", "name": "1987 Flex"},
            ]
        }
        requests_get_mock.return_value = response_mock

        with self.assertLogs("apps.catalog.fipe_service", level="WARNING") as captured_logs:
            fuel_values = get_fuel_options_for_model(brand_name="Ford", model_name="Ka", force_refresh=True)

        self.assertEqual(fuel_values, ["Gasolina", "Flex"])
        self.assertTrue(any("fallback list extraction" in message for message in captured_logs.output))

    @override_settings(FIPE_API_TOKEN="token-teste")
    @patch("apps.catalog.fipe_service.requests.get")
    def test_get_fuel_options_logs_invalid_payload_preview(self, requests_get_mock: Mock) -> None:
        brand = FipeVehicleBrand.objects.create(name="Ford", external_id="22")
        FipeVehicleModel.objects.create(brand=brand, vehicle_type=brand.vehicle_type, name="Ka", external_id="664")

        response_mock = Mock()
        response_mock.json.return_value = {"message": "token invalido", "success": False}
        requests_get_mock.return_value = response_mock

        with self.assertLogs("apps.catalog.fipe_service", level="ERROR") as captured_logs:
            with self.assertRaises(ValueError):
                get_fuel_options_for_model(brand_name="Ford", model_name="Ka", force_refresh=True)

        self.assertTrue(any("payload_preview" in message for message in captured_logs.output))
        self.assertTrue(any("token invalido" in message for message in captured_logs.output))


class CatalogFipeApiTests(TestCase):
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
        response = self.client.get(reverse("catalog:fipe-models"), {"brand": "Ford"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{"id": "Ka", "label": "Ka"}])

    def test_fipe_fuels_endpoint_returns_cached_fuels(self) -> None:
        response = self.client.get(reverse("catalog:fipe-fuels"), {"brand": "Ford", "model": "Ka"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{"id": "Gasolina", "label": "Gasolina"}, {"id": "Flex", "label": "Flex"}])

    @patch("apps.catalog.views.kits.get_fuel_options_for_model")
    def test_fipe_fuels_endpoint_returns_inferred_fuel_without_fipe_fallback(self, get_fuel_options_mock: Mock) -> None:
        response = self.client.get(reverse("catalog:fipe-fuels"), {"brand": "Jeep", "model": "Commander 2.2 TD 4x4 Diesel Aut"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [{"id": "Diesel", "label": "Diesel"}])
        get_fuel_options_mock.assert_not_called()

    def test_service_money_fields_work_with_only_including_currency_fields(self):
        """Regressão: `djmoney` precisa do campo `*_currency` junto com o valor.

        Em alguns fluxos (ex.: HTMX do modal de Kits) usamos `.only(...)`.
        Se não incluirmos `*_currency`, acessar `service.suggested_cost` pode quebrar
        durante renderização de template.
        """

        service = Service.objects.create(
            workshop=self.workshop,
            name="Serviço 1",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=Money(5, "BRL"),
            is_third_party=False,
            is_active=True,
        )

        s = Service.objects.only(
            "id",
            "name",
            "suggested_cost",
            "suggested_cost_currency",
            "selling_price",
            "selling_price_currency",
        ).get(pk=service.pk)

        # Não deve levantar exceção
        self.assertEqual(str(s.suggested_cost), "R$\xa05,00")
        self.assertEqual(str(s.selling_price), "R$\xa010,00")


class KitFormPageTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=77)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_kit_create_page_resets_modal_results_and_edit_modal_state(self) -> None:
        response = self.client.get(reverse("catalog:kits_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Opcional: informe os veículos, motorizações e anos compatíveis com este kit.")
        self.assertContains(response, "Nenhuma aplicação adicionada.")
        self.assertContains(response, "Inserir tempo total do Kit")
        self.assertContains(response, "Inserir Valor Total Venda Serviços")
        self.assertNotContains(response, "Distribuir Tempos")
        self.assertContains(response, "Total dos produtos")
        self.assertContains(response, "Total dos serviços")
        self.assertContains(response, "Valor de venda por tempo")
        self.assertContains(response, "Valor de Venda Inserido")
        self.assertContains(response, "Custo local do kit")
        self.assertContains(response, "Esse valor e recalculado automaticamente com base na duração do serviço.")
        self.assertContains(response, "Deixe vazio para usar o custo por duração")
        self.assertContains(response, "servicePricingColumnClasses('by_duration', 'header')", html=False)
        self.assertContains(response, "servicePricingColumnClasses('inserted_value', 'header')", html=False)
        self.assertContains(response, "servicePricingColumnClasses(mode, section = 'body')", html=False)
        self.assertContains(response, "servicePricingMode: 'by_duration'", html=False)
        self.assertContains(response, "this.reloadProductSuggestions();", html=False)
        self.assertContains(response, "this.reloadServiceSuggestions();", html=False)
        self.assertContains(response, "Carregando produto...", html=False)
        self.assertContains(response, "Editar serviço do kit")
        self.assertContains(response, "Selecione um item para editar.", html=False)
        self.assertContains(response, '@kit-service-updated.window="applyUpdatedService($event.detail)"', html=False)
        self.assertContains(response, "baseEngineOptions:", html=False)
        self.assertContains(response, "syncApplicationEngineFromModel(index);", html=False)
        self.assertContains(response, 'name="kit_application_engine"', html=False)
        self.assertContains(response, "application.engineLocked", html=False)
        self.assertContains(response, 'name="kit_application_fuel"', html=False)
        self.assertContains(response, "onApplicationBrandChange(index)", html=False)
        self.assertContains(response, "/catalog/fipe/fuels/", html=False)
        self.assertNotContains(response, "window.htmx.trigger(list, 'load');", html=False)


class KitListViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=81)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_kit_list_renders_expandable_application_preview(self) -> None:
        kit = Kit.objects.create(workshop=self.workshop, name="Kit Aplicacoes", description="", is_active=True)
        KitApplication.objects.create(kit=kit, brand="Jeep", model="Renegade", engine="2.0", fuel="Diesel", year_start=2015, year_end=2021)
        KitApplication.objects.create(kit=kit, brand="Fiat", model="Toro", engine="2.0", fuel="Diesel", year_start=2016, year_end=2022)
        KitApplication.objects.create(kit=kit, brand="Ram", model="Rampage", engine="2.0", fuel="Diesel", year_start=2024, year_end=2024)

        response = self.client.get(reverse("catalog:kits_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jeep Renegade")
        self.assertContains(response, "2.0 Diesel | 2015 a 2021")
        self.assertContains(response, "Fiat Toro")
        self.assertContains(response, "2.0 Diesel | 2016 a 2022")
        self.assertContains(response, "Ram Rampage")
        self.assertContains(response, "2.0 Diesel | 2024")
        self.assertContains(response, "Ver mais")
        self.assertContains(response, "Ver menos")
        self.assertContains(response, "+1")
        self.assertNotContains(response, "Jeep Renegade 2.0 Diesel 2015 a 2021; +2")
        self.assertLess(response.content.decode().find("Ram Rampage"), response.content.decode().find("Ver menos"))

    def test_kit_list_search_still_matches_application_fields(self) -> None:
        matching_kit = Kit.objects.create(workshop=self.workshop, name="Kit Diesel", description="", is_active=True)
        KitApplication.objects.create(kit=matching_kit, brand="Fiat", model="Toro", engine="2.0", fuel="Diesel", year_start=2016, year_end=2022)

        other_kit = Kit.objects.create(workshop=self.workshop, name="Kit Gasolina", description="", is_active=True)
        KitApplication.objects.create(kit=other_kit, brand="Honda", model="Civic", engine="1.5", fuel="Gasolina", year_start=2019, year_end=2021)

        response = self.client.get(reverse("catalog:kits_list"), data={"q": "Toro"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, matching_kit.name)
        self.assertNotContains(response, other_kit.name)


class ServiceQuickUpdateViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=79)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.service = Service.objects.create(
            workshop=self.workshop,
            name="Servico Original",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money("50.00", "BRL"),
            suggested_cost=Money("20.00", "BRL"),
            is_third_party=False,
            is_active=True,
        )

    def test_service_quick_update_triggers_kit_service_updated_event(self) -> None:
        response = self.client.post(
            reverse("catalog:edit_service_modal_form", args=[self.service.pk]),
            data={
                "name": "Servico Atualizado",
                "is_third_party": "",
                "duration": "01:15:00",
                "selling_price_0": "80.00",
                "selling_price_1": "BRL",
                "suggested_cost_0": "35.00",
                "suggested_cost_1": "BRL",
                "description": "Atualizado",
                "is_active": "on",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        self.assertIn("HX-Trigger", response.headers)

        trigger_payload = json.loads(response.headers["HX-Trigger"])
        self.assertIn("kit-service-updated", trigger_payload)
        self.assertEqual(
            trigger_payload["kit-service-updated"],
            {
                "id": self.service.pk,
                "name": "Servico Atualizado",
                "cost": str(Money("35.00", "BRL")),
                "sell": str(Money("80.00", "BRL")),
                "duration": "01:15:00",
            },
        )


class KitServiceBulkPricingViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=80)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.service = Service.objects.create(
            workshop=self.workshop,
            name="Servico Rateado",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money("50.00", "BRL"),
            suggested_cost=Money("20.00", "BRL"),
            is_third_party=False,
            is_active=True,
        )

    def test_bulk_pricing_returns_recalculated_selling_prices(self) -> None:
        today = timezone.now()
        WorkshopCost.objects.create(
            workshop=self.workshop,
            month=today.month,
            year=today.year,
            mechanic_quantity=1,
            minimum_hourly_cost=Money("30.00", "BRL"),
            hourly_cost_value=Money("80.00", "BRL"),
        )

        response = self.client.post(
            reverse("catalog:kits_service_bulk_pricing"),
            data=json.dumps({"services": [{"id": self.service.pk, "duration": "01:30:00"}]}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            {
                "services": [{"id": self.service.pk, "cost": str(Money("45.00", "BRL")), "sell": str(Money("120.00", "BRL"))}],
                "workshop_cost_missing": False,
            },
        )

    def test_bulk_pricing_warns_when_workshop_cost_is_missing(self) -> None:
        response = self.client.post(
            reverse("catalog:kits_service_bulk_pricing"),
            data=json.dumps({"services": [{"id": self.service.pk, "duration": "01:30:00"}]}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            {
                "services": [],
                "workshop_cost_missing": True,
            },
        )


class KitServiceLocalUpdateViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=82)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.kit = Kit.objects.create(workshop=self.workshop, name="Kit Persistencia", description="", is_active=True)
        self.service = Service.objects.create(
            workshop=self.workshop,
            name="Servico Persistido",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money("20.00", "BRL"),
            suggested_cost=Money("10.00", "BRL"),
            is_third_party=False,
            is_active=True,
        )
        self.kit_service = KitService.objects.create(
            kit=self.kit,
            service=self.service,
            quantity=1,
            duration=self.service.duration,
            duration_selling_price=Money("25.00", "BRL"),
            selling_price=Money("30.00", "BRL"),
        )

    def test_local_update_persists_service_changes_for_reload(self) -> None:
        response = self.client.post(
            reverse("catalog:kits_service_local_update", args=[self.kit.pk, self.service.pk]),
            data=json.dumps(
                {
                    "qty": 1,
                    "duration": "01:15:00",
                    "cost": "18.50",
                    "sell_by_duration": "99.90",
                    "sell": "120.00",
                    "service_pricing_mode": Kit.ServicePricingMode.BY_DURATION,
                }
            ),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)

        self.kit_service.refresh_from_db()
        self.kit.refresh_from_db()

        self.assertEqual(self.kit_service.duration, datetime.timedelta(hours=1, minutes=15))
        self.assertEqual(self.kit_service.cost_price, Money("18.50", "BRL"))
        self.assertEqual(self.kit_service.duration_selling_price, Money("99.90", "BRL"))
        self.assertEqual(self.kit_service.selling_price, Money("120.00", "BRL"))
        self.assertEqual(self.kit.service_pricing_mode, Kit.ServicePricingMode.BY_DURATION)
        self.assertEqual(self.kit.total_price, Money("99.90", "BRL"))

    def test_services_sync_persists_bulk_state_for_reload(self) -> None:
        response = self.client.post(
            reverse("catalog:kits_services_sync", args=[self.kit.pk]),
            data=json.dumps(
                {
                    "service_pricing_mode": Kit.ServicePricingMode.INSERTED_VALUE,
                    "services": [
                        {
                            "id": self.service.pk,
                            "qty": 2,
                            "duration": "01:10:00",
                            "cost": "15.00",
                            "sell_by_duration": "88.00",
                            "sell": "111.00",
                        }
                    ],
                }
            ),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)

        self.kit_service.refresh_from_db()
        self.kit.refresh_from_db()

        self.assertEqual(self.kit_service.quantity, 2)
        self.assertEqual(self.kit_service.duration, datetime.timedelta(hours=1, minutes=10))
        self.assertEqual(self.kit_service.cost_price, Money("15.00", "BRL"))
        self.assertEqual(self.kit_service.duration_selling_price, Money("88.00", "BRL"))
        self.assertEqual(self.kit_service.selling_price, Money("111.00", "BRL"))
        self.assertEqual(self.kit.service_pricing_mode, Kit.ServicePricingMode.INSERTED_VALUE)
        self.assertEqual(self.kit.total_price, Money("222.00", "BRL"))


class KitSearchPartialTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=78)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Kit Search")

    def test_product_search_partial_renders_unlocalized_ids(self) -> None:
        product = Product.objects.create(
            id=1296,
            workshop=self.workshop,
            code="PROD-KIT-1296",
            name="Produto Modal",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
            is_active=True,
        )

        response = self.client.get(reverse("catalog:kits_product_search"), data={"product_search": product.name})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ":checked=\"modalSelectedProducts.some(i => i.id == '1296')\"", html=False)
        self.assertContains(response, "id: '1296'", html=False)
        self.assertNotContains(response, "id: '1.296'", html=False)

    def test_service_search_partial_renders_unlocalized_ids(self) -> None:
        service = Service.objects.create(
            id=1296,
            workshop=self.workshop,
            name="Servico Modal",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=Money(5, "BRL"),
            is_third_party=False,
            is_active=True,
        )

        response = self.client.get(reverse("catalog:kits_service_search"), data={"service_search": service.name})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ":checked=\"modalSelectedServices.some(i => i.id == '1296')\"", html=False)
        self.assertContains(response, "id: '1296'", html=False)
        self.assertNotContains(response, "id: '1.296'", html=False)

    def test_product_search_partial_matches_without_accents_and_case(self) -> None:
        Product.objects.create(
            workshop=self.workshop,
            code="PROD-KIT-2001",
            name="Bomba Dagua",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
            is_active=True,
        )
        Product.objects.create(
            workshop=self.workshop,
            code="PROD-KIT-2002",
            name="Filtro de Ar",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
            is_active=True,
        )

        response = self.client.get(reverse("catalog:kits_product_search"), data={"product_search": "ÁGUA"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bomba dagua")
        self.assertNotContains(response, "Filtro de Ar")

    def test_equivalent_product_search_partial_renders_all_products_when_query_is_empty(self) -> None:
        Product.objects.create(
            workshop=self.workshop,
            code="PROD-EQ-3001",
            name="Produto Equivalente 1",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            brand="Marca A",
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
            is_active=True,
        )
        Product.objects.create(
            workshop=self.workshop,
            code="PROD-EQ-3002",
            name="Produto Equivalente 2",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            brand="Marca B",
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
            is_active=True,
        )

        response = self.client.get(reverse("catalog:product_search"), data={"equivalent_search": ""}, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Produto equivalente 1")
        self.assertContains(response, "Produto equivalente 2")
        self.assertContains(response, "checkbox-primary")
        self.assertContains(response, "bg-success/10 hover:bg-success/20", html=False)
        self.assertContains(response, ":disabled=\"isAppliedEquivalent('", html=False)
        self.assertContains(response, "btn btn-xs btn-error text-white")

    def test_equivalent_product_search_partial_excludes_ignored_product(self) -> None:
        ignored_product = Product.objects.create(
            workshop=self.workshop,
            code="PROD-EQ-4001",
            name="Produto Ignorado",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            brand="Marca Ignorada",
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
            is_active=True,
        )
        Product.objects.create(
            workshop=self.workshop,
            code="PROD-EQ-4002",
            name="Produto Mantido",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            brand="Marca Mantida",
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
            is_active=True,
        )

        response = self.client.get(
            reverse("catalog:product_search"),
            data={"equivalent_search": "Produto", "ignore_id": str(ignored_product.pk)},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Produto Ignorado")
        self.assertContains(response, "Produto mantido")

    def test_service_search_partial_matches_without_accents_and_case(self) -> None:
        Service.objects.create(
            workshop=self.workshop,
            name="Revisao Basica",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=Money(5, "BRL"),
            is_third_party=False,
            is_active=True,
        )
        Service.objects.create(
            workshop=self.workshop,
            name="Alinhamento",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money(10, "BRL"),
            suggested_cost=Money(5, "BRL"),
            is_third_party=False,
            is_active=True,
        )

        response = self.client.get(reverse("catalog:kits_service_search"), data={"service_search": "REVISÃO"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Revisao Basica")
        self.assertNotContains(response, "Alinhamento")


class KitCompatibilityEvaluationTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(name="Oficina Compatibilidade", phone="+5511999999999", address="Rua Compatibilidade, 123")
        self.customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Compatibilidade",
            cpf_or_cnpj="123.456.789-10",
            email="compatibilidade@example.com",
            phone="+5511888888888",
        )

    def _create_vehicle(
        self,
        *,
        brand: str = "Jeep",
        model: str = "Renegade",
        year_fabrication: str = "2020",
        year_model: str = "2020",
        engine: str = "2.0",
        fuel: str = "Diesel",
    ) -> Vehicle:
        return Vehicle.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            plate="KIT1234",
            brand=brand,
            model=model,
            year_fabrication=year_fabrication,
            year_model=year_model,
            color="Prata",
            engine=engine,
            fuel=fuel,
        )

    def _create_kit(
        self,
        *,
        brand: str = "Jeep",
        model: str = "Renegade",
        engine: str = "2.0",
        fuel: str = "Diesel",
        year_start: int = 2015,
        year_end: int = 2021,
    ) -> Kit:
        kit = Kit.objects.create(workshop=self.workshop, name=f"Kit Compatibilidade {Kit.objects.count() + 1}")
        KitApplication.objects.create(
            kit=kit,
            brand=brand,
            model=model,
            engine=engine,
            fuel=fuel,
            year_start=year_start,
            year_end=year_end,
        )
        return kit

    def test_evaluate_returns_compatible_for_full_match(self) -> None:
        vehicle = self._create_vehicle()
        kit = self._create_kit()

        result = evaluate_kit_vehicle_compatibility(kit=kit, vehicle=vehicle)

        self.assertEqual(result.status, "compatible")
        self.assertEqual(result.label, "Compatível")
        self.assertTrue(result.selectable)
        self.assertTrue(result.visible_by_default)

    def test_evaluate_returns_partial_when_brand_model_and_year_match_via_fabrication_year_fallback(self) -> None:
        vehicle = self._create_vehicle(year_fabrication="2020", year_model="")
        kit = self._create_kit(engine="1.8")

        result = evaluate_kit_vehicle_compatibility(kit=kit, vehicle=vehicle)

        self.assertEqual(result.status, "partially_compatible")
        self.assertEqual(result.label, "Compatibilidade Parcial")
        self.assertEqual(result.description, "Kit com marca, modelo e ano compatíveis, mas com diferenças de motor ou combustível.")
        self.assertTrue(result.selectable)
        self.assertTrue(result.visible_by_default)

    def test_evaluate_returns_partial_when_fuel_differs(self) -> None:
        vehicle = self._create_vehicle()
        kit = self._create_kit(fuel="Flex")

        result = evaluate_kit_vehicle_compatibility(kit=kit, vehicle=vehicle)

        self.assertEqual(result.status, "partially_compatible")
        self.assertEqual(result.label, "Compatibilidade Parcial")

    def test_evaluate_returns_missing_vehicle_data_when_context_is_incomplete(self) -> None:
        vehicle = self._create_vehicle(engine="")
        kit = self._create_kit()

        result = evaluate_kit_vehicle_compatibility(kit=kit, vehicle=vehicle)

        self.assertEqual(result.status, "missing_vehicle_data")
        self.assertEqual(result.label, "Compatibilidade indeterminada")
        self.assertTrue(result.selectable)
        self.assertTrue(result.visible_by_default)

    def test_evaluate_returns_incompatible_when_brand_model_or_year_do_not_match(self) -> None:
        vehicle = self._create_vehicle(model="Wrangler")
        kit = self._create_kit()

        result = evaluate_kit_vehicle_compatibility(kit=kit, vehicle=vehicle)

        self.assertEqual(result.status, "incompatible")
        self.assertEqual(result.label, "Incompatível")
        self.assertFalse(result.selectable)
        self.assertFalse(result.visible_by_default)

    def test_evaluate_returns_incompatible_when_model_is_only_prefix_match(self) -> None:
        vehicle = self._create_vehicle(brand="Toyota", model="Corolla")
        kit = self._create_kit(brand="Toyota", model="Corolla Cross")

        result = evaluate_kit_vehicle_compatibility(kit=kit, vehicle=vehicle)

        self.assertEqual(result.status, "incompatible")
        self.assertEqual(result.label, "Incompatível")

    def test_evaluate_returns_incompatible_when_brand_is_only_prefix_match(self) -> None:
        vehicle = self._create_vehicle(brand="Land Rover", model="Defender")
        kit = self._create_kit(brand="Rover", model="Defender")

        result = evaluate_kit_vehicle_compatibility(kit=kit, vehicle=vehicle)

        self.assertEqual(result.status, "incompatible")
        self.assertEqual(result.label, "Incompatível")


class ProductFormTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(name="Oficina Produto", phone="+5511999999999", address="Rua Produto, 123")
        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Produto")

    def test_product_form_accepts_profit_margin_value_without_digit_error(self) -> None:
        form = ProductForm(
            data={
                "code": "PROD-001",
                "name": "Produto Teste",
                "description": "",
                "unit": Product.Unit.UND,
                "group": str(self.group.pk),
                "brand": "",
                "model": "",
                "sku": "",
                "barcode": "",
                "location": "",
                "cost_price_0": "10.00",
                "cost_price_1": "BRL",
                "selling_price_0": "10.11",
                "selling_price_1": "BRL",
                "profit_margin": "1.10",
                "ncm": "87089990",
                "cest": "",
                "origin_cst": str(Product.OriginCST.NACIONAL),
                "purpose": Product.Purpose.RESALE,
                "application": "",
                "is_active": "on",
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        product = form.save(commit=False)
        self.assertEqual(product.profit_margin, Decimal("1.09"))

    def test_product_form_converts_fractional_profit_margin_to_percent_value(self) -> None:
        form = ProductForm(
            data={
                "code": "PROD-002",
                "name": "Produto Fracao",
                "description": "",
                "unit": Product.Unit.UND,
                "group": str(self.group.pk),
                "brand": "",
                "model": "",
                "sku": "",
                "barcode": "",
                "location": "",
                "cost_price_0": "10.00",
                "cost_price_1": "BRL",
                "selling_price_0": "20.00",
                "selling_price_1": "BRL",
                "profit_margin": "0.500000",
                "ncm": "87089990",
                "cest": "",
                "origin_cst": str(Product.OriginCST.NACIONAL),
                "purpose": Product.Purpose.RESALE,
                "application": "",
                "is_active": "on",
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        product = form.save(commit=False)
        self.assertEqual(product.profit_margin, Decimal("50.00"))

    def test_product_form_requires_confirmation_for_price_below_last_used_price(self) -> None:
        product = Product.objects.create(
            workshop=self.workshop,
            code="PROD-003",
            name="Produto Historico",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("40.00", "BRL"),
            last_used_price=Money("30.00", "BRL"),
            ncm="87089990",
        )

        form = ProductForm(
            instance=product,
            data={
                "code": product.code,
                "name": product.name,
                "description": "",
                "unit": Product.Unit.UND,
                "group": str(self.group.pk),
                "brand": "",
                "model": "",
                "sku": "",
                "barcode": "",
                "location": "",
                "cost_price_0": "10.00",
                "cost_price_1": "BRL",
                "selling_price_0": "20.00",
                "selling_price_1": "BRL",
                "profit_margin": "50.00",
                "ncm": "87089990",
                "cest": "",
                "origin_cst": str(Product.OriginCST.NACIONAL),
                "purpose": Product.Purpose.RESALE,
                "application": "",
                "is_active": "on",
            },
            workshop=self.workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Último valor usado: R$ 30,00", str(form.errors["selling_price"][0]))

    def test_product_form_allows_confirmed_price_below_last_used_price(self) -> None:
        product = Product.objects.create(
            workshop=self.workshop,
            code="PROD-004",
            name="Produto Historico Confirmado",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("40.00", "BRL"),
            last_used_price=Money("30.00", "BRL"),
            ncm="87089990",
        )

        form = ProductForm(
            instance=product,
            data={
                "code": product.code,
                "name": product.name,
                "description": "",
                "unit": Product.Unit.UND,
                "group": str(self.group.pk),
                "brand": "",
                "model": "",
                "sku": "",
                "barcode": "",
                "location": "",
                "cost_price_0": "10.00",
                "cost_price_1": "BRL",
                "selling_price_0": "20.00",
                "selling_price_1": "BRL",
                "profit_margin": "50.00",
                "ncm": "87089990",
                "cest": "",
                "origin_cst": str(Product.OriginCST.NACIONAL),
                "purpose": Product.Purpose.RESALE,
                "application": "",
                "is_active": "on",
                "confirm_lower_price": "1",
            },
            workshop=self.workshop,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())

    def test_product_form_modal_does_not_render_nested_form(self) -> None:
        html = render_crispy_form(ProductForm(workshop=self.workshop))

        self.assertEqual(html.count("<form"), 1)
        self.assertNotIn('method="dialog"', html)
        self.assertIn('id="submit-id-submit"', html)
        self.assertIn('class="input-theme border-none bg-base-100 textinput', html)

    def test_product_form_create_hides_equivalent_products_save_button(self) -> None:
        Product.objects.create(
            workshop=self.workshop,
            code="PROD-EQ-FORM-001",
            name="Produto Formulario",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            brand="Marca Formulario",
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
            is_active=True,
        )

        html = render_crispy_form(ProductForm(workshop=self.workshop))

        self.assertNotIn("Salvar Produtos Equivalentes", html)
        self.assertIn("isAppliedEquivalent", html)
        self.assertIn("removeAppliedEquivalent", html)
        self.assertIn("submittedEquivalentProducts()", html)
        self.assertIn("bg-success/10 hover:bg-success/20", html)
        self.assertNotIn("Produtos equivalentes salvos no formulário", html)
        self.assertIn("Os produtos equivalentes serão salvos quando você salvar o produto.", html)
        self.assertIn("Produto formulario", html)
        self.assertIn("Marca formulario", html)

    def test_product_form_update_renders_equivalent_products_persist_controls(self) -> None:
        equivalent_product = Product.objects.create(
            workshop=self.workshop,
            code="PROD-EQ-FORM-002",
            name="Produto Persistencia",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            brand="Marca Persistencia",
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
            is_active=True,
        )
        product = Product.objects.create(
            workshop=self.workshop,
            code="PROD-EQ-FORM-003",
            name="Produto Atualizacao",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
            is_active=True,
        )
        product.equivalent_parts.add(equivalent_product)

        html = render_crispy_form(ProductForm(workshop=self.workshop, instance=product))

        self.assertIn("Salvar Produtos Equivalentes", html)
        self.assertIn("Produtos equivalentes salvos com sucesso.", html)
        self.assertIn("isPersistingEquivalentProducts", html)
        self.assertIn(reverse("catalog:product-equivalents-sync-hx", kwargs={"product_id": product.pk}), html)
        self.assertIn("Seleção sincronizada com o banco de dados.", html)

    def test_quick_product_edit_form_renders_white_equivalent_search_field(self) -> None:
        product = Product.objects.create(
            workshop=self.workshop,
            code="PROD-EQ-FORM-004",
            name="Produto Modal",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
            is_active=True,
        )

        html = render_crispy_form(QuickProductEditForm(workshop=self.workshop, instance=product))

        self.assertIn('class="input-theme border-none bg-base-100 textinput', html)
        self.assertIn("Salvar Produtos Equivalentes", html)


class ProductUpdateNavigationTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=31)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Navegacao")
        self.product = Product.objects.create(
            workshop=self.workshop,
            code="PROD-NAV-001",
            name="Produto Navegacao",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
        )

    def test_product_update_uses_next_url_for_back_and_success(self) -> None:
        next_url = "/emissao/?step=6"

        response = self.client.get(reverse("catalog:product_update", kwargs={"pk": self.product.pk}), data={"next": next_url})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{next_url}"')
        self.assertContains(response, f'href="{next_url}" class="btn-form-cancel"')

        response = self.client.post(
            f"{reverse('catalog:product_update', kwargs={'pk': self.product.pk})}?next=%2Femissao%2F%3Fstep%3D6",
            data={
                "code": self.product.code,
                "name": "Produto Navegacao Atualizado",
                "description": "",
                "unit": Product.Unit.UND,
                "group": str(self.group.pk),
                "brand": "",
                "model": "",
                "sku": "",
                "barcode": "",
                "location": "",
                "cost_price_0": "10.00",
                "cost_price_1": "BRL",
                "selling_price_0": "20.00",
                "selling_price_1": "BRL",
                "profit_margin": "50.00",
                "ncm": "87089990",
                "cest": "",
                "origin_cst": str(Product.OriginCST.NACIONAL),
                "purpose": Product.Purpose.RESALE,
                "application": "",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), next_url)

    def test_product_update_renders_lower_price_confirmation_modal(self) -> None:
        self.product.last_used_price = Money("30.00", "BRL")
        self.product.save(update_fields=["last_used_price"])

        response = self.client.get(reverse("catalog:product_update", kwargs={"pk": self.product.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="product-lower-price-modal"', html=False)
        self.assertContains(response, '@click="continueWithLowerPrice()"', html=False)
        self.assertNotContains(response, 'x-show="lowerPriceWarning"', html=False)


class ProductEquivalentSyncHXViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=33)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Equivalentes")
        self.product = Product.objects.create(
            workshop=self.workshop,
            code="PROD-EQ-SYNC-001",
            name="Produto Base",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
        )

    def test_product_equivalent_sync_endpoint_persists_selection(self) -> None:
        equivalent_product_a = Product.objects.create(
            workshop=self.workshop,
            code="PROD-EQ-SYNC-002",
            name="Produto Equivalente A",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            brand="Marca A",
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
        )
        equivalent_product_b = Product.objects.create(
            workshop=self.workshop,
            code="PROD-EQ-SYNC-003",
            name="Produto Equivalente B",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            brand="Marca B",
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
        )

        response = self.client.post(
            reverse("catalog:product-equivalents-sync-hx", kwargs={"product_id": self.product.pk}),
            data=json.dumps({"equivalent_ids": [str(equivalent_product_b.pk), str(equivalent_product_a.pk)]}),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(self.product.equivalent_parts.order_by("name", "code").values_list("id", flat=True)), [equivalent_product_a.pk, equivalent_product_b.pk])
        self.assertTrue(equivalent_product_a.equivalent_parts.filter(pk=self.product.pk).exists())

        payload = response.json()
        self.assertEqual(payload["message"], "Produtos equivalentes salvos com sucesso.")
        self.assertEqual([item["id"] for item in payload["equivalents"]], [str(equivalent_product_b.pk), str(equivalent_product_a.pk)])

    def test_product_equivalent_sync_endpoint_can_clear_existing_relations(self) -> None:
        equivalent_product = Product.objects.create(
            workshop=self.workshop,
            code="PROD-EQ-SYNC-004",
            name="Produto Equivalente C",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("20.00", "BRL"),
            profit_margin=Decimal("50.00"),
            ncm="87089990",
        )
        self.product.equivalent_parts.add(equivalent_product)

        response = self.client.post(
            reverse("catalog:product-equivalents-sync-hx", kwargs={"product_id": self.product.pk}),
            data=json.dumps({"equivalent_ids": []}),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.product.equivalent_parts.exists())
        self.assertEqual(response.json()["equivalents"], [])

    def test_product_equivalent_sync_endpoint_rejects_self_reference(self) -> None:
        response = self.client.post(
            reverse("catalog:product-equivalents-sync-hx", kwargs={"product_id": self.product.pk}),
            data=json.dumps({"equivalent_ids": [str(self.product.pk)]}),
            content_type="application/json",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "O produto não pode ser equivalente a ele mesmo.")
        self.assertFalse(self.product.equivalent_parts.exists())


class ProductKitAssignmentTabTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=32)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Atribuicao Kit")
        self.product = Product.objects.create(
            workshop=self.workshop,
            code="PROD-KIT-001",
            name="Produto Kit",
            description="",
            unit=Product.Unit.UND,
            group=self.group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("25.00", "BRL"),
            profit_margin=Decimal("60.00"),
            ncm="87089990",
        )

    def test_product_update_tab_lists_all_kits_with_pagination_and_assigned_state(self) -> None:
        [Kit.objects.create(workshop=self.workshop, name=f"Kit {index:02d}", description="", is_active=True) for index in range(1, 11)]
        assigned_kit = Kit.objects.create(workshop=self.workshop, name="Kit Zebra", description="", is_active=True)
        Kit.objects.create(workshop=self.workshop, name="Kit ZZ Extra", description="", is_active=True)
        KitProduct.objects.create(kit=assigned_kit, product=self.product, quantity=1)

        response = self.client.get(reverse("catalog:product_update", kwargs={"pk": self.product.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kit zebra")
        self.assertContains(response, "Kit 01")
        self.assertNotContains(response, "Kit ZZ Extra")
        self.assertContains(response, "Página 1 de 2")
        self.assertContains(response, "Produto já atribuído")
        self.assertContains(response, "Remover atribuição")
        self.assertContains(response, 'id="product-kits-search-form"', html=False)
        self.assertContains(response, 'id="product-kits-search"', html=False)
        self.assertContains(response, "Buscar")
        self.assertNotContains(response, 'hx-trigger="input changed delay:300ms, search"', html=False)
        self.assertContains(response, 'class="flex flex-wrap items-center justify-between gap-3 pt-1"', html=False)
        self.assertContains(response, 'class="btn btn-sm btn-primary"', html=False)
        self.assertContains(response, 'class="flex flex-wrap items-center justify-between gap-3"', html=False)
        self.assertContains(response, 'class="min-w-0 flex-1"', html=False)
        self.assertContains(response, 'class="shrink-0"', html=False)
        self.assertContains(response, 'class="btn btn-xs btn-error text-white"', html=False)
        self.assertLess(response.content.decode().find("Kit zebra"), response.content.decode().find("Kit 01"))

    def test_product_kits_list_endpoint_filters_by_search_and_preserves_pending_selection(self) -> None:
        Kit.objects.create(workshop=self.workshop, name="Kit Alinhamento", description="", is_active=True)
        selected_kit = Kit.objects.create(workshop=self.workshop, name="Kit Freio Premium", description="", is_active=True)

        response = self.client.get(
            reverse("catalog:kits-by-product-hx", kwargs={"product_id": self.product.pk}),
            data={"q": "Freio", "selected_kits": [str(selected_kit.pk)]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kit freio premium")
        self.assertNotContains(response, "Kit Alinhamento")
        self.assertContains(response, "Selecionado para atribuição")
        self.assertContains(response, "selectedKitIds: [")

    def test_product_kits_assign_endpoint_creates_assignment_and_recalculates_total(self) -> None:
        kit = Kit.objects.create(workshop=self.workshop, name="Kit Suspensao", description="", is_active=True)

        response = self.client.post(
            reverse("catalog:product-kits-assign-hx", kwargs={"product_id": self.product.pk}),
            data={"selected_kits": [str(kit.pk)], "page": "1", "q": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(KitProduct.objects.filter(kit=kit, product=self.product, quantity=1).exists())

        kit.refresh_from_db()
        self.assertEqual(kit.total_price, Money("25.00", "BRL"))
        self.assertContains(response, "Produto já atribuído")
        self.assertIn("Produto atribuido a 1 kit(s) com sucesso.", response.headers.get("HX-Trigger", ""))

    def test_product_kit_unassign_endpoint_removes_assignment_and_recalculates_total(self) -> None:
        kit = Kit.objects.create(workshop=self.workshop, name="Kit Revisao", description="", is_active=True)
        service = Service.objects.create(
            workshop=self.workshop,
            name="Servico Base",
            description="",
            duration=datetime.timedelta(minutes=30),
            selling_price=Money("15.00", "BRL"),
            suggested_cost=Money("5.00", "BRL"),
            is_third_party=False,
            is_active=True,
        )
        KitService.objects.create(kit=kit, service=service, quantity=1, duration=datetime.timedelta(minutes=30))
        KitProduct.objects.create(kit=kit, product=self.product, quantity=1)
        recalculate_kit_totals(kit)

        response = self.client.post(
            reverse("catalog:product-kit-unassign-hx", kwargs={"product_id": self.product.pk, "kit_id": kit.pk}),
            data={"page": "1", "q": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(KitProduct.objects.filter(kit=kit, product=self.product).exists())

        kit.refresh_from_db()
        self.assertEqual(kit.total_price, Money("15.00", "BRL"))
        self.assertNotContains(response, "Produto já atribuído")
        self.assertIn("Atribuicao removida com sucesso.", response.headers.get("HX-Trigger", ""))
