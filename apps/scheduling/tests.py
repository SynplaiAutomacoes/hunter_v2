from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account, User
from apps.collaborators.models import WorkshopMember
from apps.customer.models import Customer, Vehicle
from apps.iam.utils import get_or_create_director_role
from apps.scheduling.models import Appointment
from apps.workshops.models.workshops import Workshop


def create_director_user_with_workshop(*, suffix: int = 1) -> tuple[User, Workshop]:
    user = User.objects.create_user(username=f"scheduling-director{suffix}", password="123", cpf=f"99111222{suffix:03d}")
    account = Account.objects.create(name=f"Conta Scheduling {suffix}", owner=user)
    user.account = account
    user.is_account_owner = True
    user.save(update_fields=["account", "is_account_owner"])

    workshop = Workshop.objects.create(
        account=account,
        name=f"Oficina Scheduling {suffix}",
        cnpj=f"19.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Scheduling, 100",
    )

    director_role = get_or_create_director_role(account=account, with_all_permissions=True)
    WorkshopMember.objects.create(user=user, workshop=workshop, role=director_role, is_active=True)
    return user, workshop


def create_customer(*, workshop: Workshop, suffix: int = 1) -> Customer:
    return Customer.objects.create(
        workshop=workshop,
        name=f"Cliente Agenda {suffix}",
        cpf_or_cnpj=f"123.456.789-{suffix:02d}",
        email=f"cliente.scheduling{suffix}@example.com",
        phone="+5511999999999",
    )


def create_vehicle(*, workshop: Workshop, customer: Customer, suffix: int = 1, plate: str | None = None) -> Vehicle:
    return Vehicle.objects.create(
        workshop=workshop,
        customer=customer,
        plate=plate or f"SCD1A{suffix:02d}",
        brand="Marca",
        model=f"Modelo {suffix}",
        year_fabrication="2024",
        year_model="2024",
        color="Prata",
    )


class AppointmentModelValidationTests(TestCase):
    def test_rejects_overlap_for_same_vehicle(self) -> None:
        user, workshop = create_director_user_with_workshop(suffix=10)
        customer = create_customer(workshop=workshop, suffix=10)
        vehicle = create_vehicle(workshop=workshop, customer=customer, suffix=10)

        starts_at = timezone.now().replace(minute=0, second=0, microsecond=0)
        Appointment.objects.create(
            workshop=workshop,
            customer=customer,
            vehicle=vehicle,
            title="Primeiro",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )

        overlapping = Appointment(
            workshop=workshop,
            customer=customer,
            vehicle=vehicle,
            title="Segundo",
            starts_at=starts_at + timedelta(minutes=30),
            ends_at=starts_at + timedelta(hours=1, minutes=30),
        )

        with self.assertRaises(ValidationError):
            overlapping.full_clean()

        self.assertTrue(User.objects.filter(pk=user.pk).exists())

    def test_allows_adjacent_slots_for_same_vehicle(self) -> None:
        _, workshop = create_director_user_with_workshop(suffix=11)
        customer = create_customer(workshop=workshop, suffix=11)
        vehicle = create_vehicle(workshop=workshop, customer=customer, suffix=11)

        starts_at = timezone.now().replace(minute=0, second=0, microsecond=0)
        Appointment.objects.create(
            workshop=workshop,
            customer=customer,
            vehicle=vehicle,
            title="Primeiro",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )

        adjacent = Appointment(
            workshop=workshop,
            customer=customer,
            vehicle=vehicle,
            title="Segundo",
            starts_at=starts_at + timedelta(hours=1),
            ends_at=starts_at + timedelta(hours=2),
        )

        adjacent.full_clean()

    def test_requires_guest_name_and_phone_when_customer_is_not_registered(self) -> None:
        _, workshop = create_director_user_with_workshop(suffix=12)
        starts_at = timezone.now().replace(minute=0, second=0, microsecond=0)

        appointment = Appointment(
            workshop=workshop,
            title="Sem cadastro",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )

        with self.assertRaises(ValidationError) as exc_info:
            appointment.full_clean()

        self.assertIn("guest_customer_name", exc_info.exception.message_dict)
        self.assertIn("guest_customer_cpf", exc_info.exception.message_dict)
        self.assertIn("guest_customer_phone", exc_info.exception.message_dict)
        self.assertIn("guest_vehicle_plate", exc_info.exception.message_dict)
        self.assertIn("guest_vehicle_brand", exc_info.exception.message_dict)
        self.assertIn("guest_vehicle_model", exc_info.exception.message_dict)
        self.assertIn("guest_vehicle_year_fabrication", exc_info.exception.message_dict)
        self.assertIn("guest_vehicle_year_model", exc_info.exception.message_dict)
        self.assertIn("guest_vehicle_engine", exc_info.exception.message_dict)
        self.assertIn("guest_vehicle_fuel", exc_info.exception.message_dict)


class AppointmentViewsTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=30)
        self.customer = create_customer(workshop=self.workshop, suffix=30)
        self.vehicle = create_vehicle(workshop=self.workshop, customer=self.customer, suffix=30)

        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_events_endpoint_respects_active_workshop_and_range(self) -> None:
        base_start = timezone.now().replace(minute=0, second=0, microsecond=0)
        Appointment.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.vehicle,
            title="Troca de Oleo",
            starts_at=base_start,
            ends_at=base_start + timedelta(hours=1),
        )

        other_customer = create_customer(workshop=self.workshop, suffix=31)
        other_vehicle = create_vehicle(workshop=self.workshop, customer=other_customer, suffix=31)
        Appointment.objects.create(
            workshop=self.workshop,
            customer=other_customer,
            vehicle=other_vehicle,
            title="Fora do Range",
            starts_at=base_start + timedelta(days=5),
            ends_at=base_start + timedelta(days=5, hours=1),
        )

        other_workshop = Workshop.objects.create(
            account=self.workshop.account,
            name="Outra oficina",
            cnpj="21.333.444/0001-21",
            phone="+5511888888888",
            address="Rua Outra, 1",
        )
        other_customer2 = create_customer(workshop=other_workshop, suffix=32)
        other_vehicle2 = create_vehicle(workshop=other_workshop, customer=other_customer2, suffix=32)
        Appointment.objects.create(
            workshop=other_workshop,
            customer=other_customer2,
            vehicle=other_vehicle2,
            title="Outra oficina",
            starts_at=base_start,
            ends_at=base_start + timedelta(hours=1),
        )

        response = self.client.get(
            reverse("scheduling:appointment_events"),
            {
                "start": base_start.isoformat(),
                "end": (base_start + timedelta(days=1)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["title"], "Troca de Oleo - Cliente Agenda 30")
        self.assertEqual(payload[0]["start"], timezone.localtime(base_start).isoformat())
        self.assertEqual(payload[0]["end"], timezone.localtime(base_start + timedelta(hours=1)).isoformat())

    def test_events_endpoint_serializes_start_and_end_in_local_timezone(self) -> None:
        local_tz = timezone.get_current_timezone()
        starts_at = timezone.make_aware(datetime(2026, 4, 3, 9, 0), local_tz)
        ends_at = timezone.make_aware(datetime(2026, 4, 3, 10, 0), local_tz)
        Appointment.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.vehicle,
            title="Horario Local",
            starts_at=starts_at,
            ends_at=ends_at,
        )

        response = self.client.get(
            reverse("scheduling:appointment_events"),
            {
                "start": starts_at.isoformat(),
                "end": (ends_at + timedelta(hours=1)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["start"], "2026-04-03T09:00:00-03:00")
        self.assertEqual(payload[0]["end"], "2026-04-03T10:00:00-03:00")

    def test_create_allows_registered_customer_without_vehicle(self) -> None:
        starts_at = timezone.now().replace(minute=0, second=0, microsecond=0)
        response = self.client.post(
            reverse("scheduling:appointment_create"),
            {
                "title": "Agendamento sem veiculo",
                "is_customer_registered": "on",
                "customer": str(self.customer.pk),
                "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (starts_at + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "block_color": "#0ea5e9",
                "status": "scheduled",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        appointment = Appointment.objects.get()
        self.assertEqual(appointment.customer, self.customer)
        self.assertIsNone(appointment.vehicle)

    def test_create_allows_guest_customer_without_registered_customer(self) -> None:
        starts_at = timezone.now().replace(minute=0, second=0, microsecond=0)
        response = self.client.post(
            reverse("scheduling:appointment_create"),
            {
                "title": "Agendamento avulso",
                "guest_customer_name": "Cliente balcAo",
                "guest_customer_cpf": "529.982.247-25",
                "guest_customer_phone": "+5511999990000",
                "guest_vehicle_plate": "abc1d23",
                "guest_vehicle_brand": "fiat",
                "guest_vehicle_model": "argo",
                "guest_vehicle_year_fabrication": "2023",
                "guest_vehicle_year_model": "2024",
                "guest_vehicle_engine": "1.3 flex",
                "guest_vehicle_fuel": "flex",
                "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (starts_at + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "block_color": "#0ea5e9",
                "status": "scheduled",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        appointment = Appointment.objects.get()
        self.assertIsNone(appointment.customer)
        self.assertIsNone(appointment.vehicle)
        self.assertEqual(appointment.guest_customer_name, "CLIENTE BALCAO")
        self.assertEqual(appointment.guest_customer_cpf, "52998224725")
        self.assertEqual(str(appointment.guest_customer_phone), "(11) 99999-0000")
        self.assertEqual(appointment.guest_vehicle_plate, "ABC1D23")
        self.assertEqual(appointment.guest_vehicle_brand, "FIAT")
        self.assertEqual(appointment.guest_vehicle_model, "ARGO")
        self.assertEqual(appointment.guest_vehicle_year_fabrication, "2023")
        self.assertEqual(appointment.guest_vehicle_year_model, "2024")
        self.assertEqual(appointment.guest_vehicle_engine, "1.3")
        self.assertEqual(appointment.guest_vehicle_fuel, "Flex")

    def test_create_rejects_invalid_guest_vehicle_engine_choice(self) -> None:
        starts_at = timezone.now().replace(minute=0, second=0, microsecond=0)
        response = self.client.post(
            reverse("scheduling:appointment_create"),
            {
                "title": "Agendamento avulso",
                "guest_customer_name": "Cliente balcAo",
                "guest_customer_cpf": "529.982.247-25",
                "guest_customer_phone": "+5511999990000",
                "guest_vehicle_plate": "abc1d23",
                "guest_vehicle_brand": "fiat",
                "guest_vehicle_model": "argo",
                "guest_vehicle_year_fabrication": "2023",
                "guest_vehicle_year_model": "2024",
                "guest_vehicle_engine": "2.8",
                "guest_vehicle_fuel": "flex",
                "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (starts_at + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "block_color": "#0ea5e9",
                "status": "scheduled",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Selecione um motor válido.")
        self.assertFalse(Appointment.objects.exists())

    def test_create_rejects_invalid_guest_vehicle_fuel_choice(self) -> None:
        starts_at = timezone.now().replace(minute=0, second=0, microsecond=0)
        response = self.client.post(
            reverse("scheduling:appointment_create"),
            {
                "title": "Agendamento avulso",
                "guest_customer_name": "Cliente balcAo",
                "guest_customer_cpf": "529.982.247-25",
                "guest_customer_phone": "+5511999990000",
                "guest_vehicle_plate": "abc1d23",
                "guest_vehicle_brand": "fiat",
                "guest_vehicle_model": "argo",
                "guest_vehicle_year_fabrication": "2023",
                "guest_vehicle_year_model": "2024",
                "guest_vehicle_engine": "1.3 flex",
                "guest_vehicle_fuel": "Gas natural",
                "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (starts_at + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "block_color": "#0ea5e9",
                "status": "scheduled",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Informe o combustivel do veiculo quando o cliente nao estiver cadastrado.")
        self.assertFalse(Appointment.objects.exists())

    def test_save_and_create_budget_without_vehicle_redirects_with_customer_only(self) -> None:
        starts_at = timezone.now().replace(minute=0, second=0, microsecond=0)
        response = self.client.post(
            reverse("scheduling:appointment_create"),
            {
                "title": "Agendamento sem veiculo",
                "is_customer_registered": "on",
                "customer": str(self.customer.pk),
                "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (starts_at + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "block_color": "#0ea5e9",
                "status": "scheduled",
                "action": "save_and_create_budget",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        appointment = Appointment.objects.get()
        self.assertEqual(response.headers.get("HX-Redirect"), f"{reverse('budget:budget_create')}?customer={self.customer.pk}&appointment_id={appointment.pk}")

    def test_save_and_create_budget_without_registered_customer_redirects_empty_budget(self) -> None:
        starts_at = timezone.now().replace(minute=0, second=0, microsecond=0)
        response = self.client.post(
            reverse("scheduling:appointment_create"),
            {
                "title": "Agendamento avulso",
                "guest_customer_name": "Cliente Balcao",
                "guest_customer_cpf": "529.982.247-25",
                "guest_customer_phone": "+5511999990000",
                "guest_vehicle_plate": "ABC1D23",
                "guest_vehicle_brand": "FIAT",
                "guest_vehicle_model": "ARGO",
                "guest_vehicle_year_fabrication": "2023",
                "guest_vehicle_year_model": "2024",
                "guest_vehicle_engine": "1.3 FLEX",
                "guest_vehicle_fuel": "FLEX",
                "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (starts_at + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "block_color": "#0ea5e9",
                "status": "scheduled",
                "action": "save_and_create_budget",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        appointment = Appointment.objects.get()
        self.assertEqual(response.headers.get("HX-Redirect"), f"{reverse('budget:budget_create')}?appointment_id={appointment.pk}")

    def test_detail_view_shows_guest_vehicle_metadata(self) -> None:
        starts_at = timezone.now().replace(minute=0, second=0, microsecond=0)
        appointment = Appointment.objects.create(
            workshop=self.workshop,
            title="Agendamento avulso",
            guest_customer_name="CLIENTE BALCAO",
            guest_customer_cpf="52998224725",
            guest_customer_phone="+5511999990000",
            guest_vehicle_plate="ABC1D23",
            guest_vehicle_brand="FIAT",
            guest_vehicle_model="ARGO",
            guest_vehicle_year_fabrication="2023",
            guest_vehicle_year_model="2024",
            guest_vehicle_engine="1.3 FLEX",
            guest_vehicle_fuel="FLEX",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )

        response = self.client.get(reverse("scheduling:appointment_detail", kwargs={"pk": appointment.pk}), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "529.982.247-25")
        self.assertContains(response, "Placa")
        self.assertContains(response, "ABC1D23")
        self.assertContains(response, "Marca")
        self.assertContains(response, "FIAT")
        self.assertContains(response, "Modelo")
        self.assertContains(response, "ARGO")
        self.assertContains(response, "Motorizacao")
        self.assertContains(response, "1.3")
        self.assertContains(response, "Combustivel")
        self.assertContains(response, "Flex")

    def test_detail_view_shows_registered_vehicle_metadata(self) -> None:
        self.vehicle.engine = "2.0 TURBO"
        self.vehicle.fuel = "GASOLINA"
        self.vehicle.save(update_fields=["engine", "fuel", "atualizado_em"])
        starts_at = timezone.now().replace(minute=0, second=0, microsecond=0)
        appointment = Appointment.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.vehicle,
            title="Cliente cadastrado",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )

        response = self.client.get(reverse("scheduling:appointment_detail", kwargs={"pk": appointment.pk}), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.vehicle.plate)
        self.assertContains(response, self.vehicle.brand)
        self.assertContains(response, self.vehicle.model)
        self.assertContains(response, "Ano Fabricacao")
        self.assertContains(response, self.vehicle.year_fabrication)
        self.assertContains(response, "Ano Modelo")
        self.assertContains(response, self.vehicle.year_model)
        self.assertContains(response, "Motorizacao")
        self.assertContains(response, "2.0")
        self.assertContains(response, "Combustivel")
        self.assertContains(response, "Gasolina")

    def test_get_vehicle_detail_returns_registered_vehicle_metadata(self) -> None:
        self.vehicle.engine = "2.0 TURBO"
        self.vehicle.fuel = "GASOLINA"
        self.vehicle.save(update_fields=["engine", "fuel", "atualizado_em"])

        response = self.client.get(reverse("scheduling:get_vehicle_detail"), {"vehicle": self.vehicle.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": self.vehicle.pk,
                "plate": self.vehicle.plate,
                "brand": self.vehicle.brand,
                "model": self.vehicle.model,
                "year_fabrication": self.vehicle.year_fabrication,
                "year_model": self.vehicle.year_model,
                "engine": "2.0",
                "fuel": "Gasolina",
            },
        )

    def test_update_form_renders_disabled_registered_vehicle_fields(self) -> None:
        self.vehicle.engine = "2.0 TURBO"
        self.vehicle.fuel = "GASOLINA"
        self.vehicle.save(update_fields=["engine", "fuel", "atualizado_em"])
        starts_at = timezone.now().replace(minute=0, second=0, microsecond=0)
        appointment = Appointment.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.vehicle,
            title="Cliente cadastrado",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )

        response = self.client.get(reverse("scheduling:appointment_update", kwargs={"pk": appointment.pk}), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dados do Veiculo Selecionado")
        self.assertContains(response, 'id="id_registered_vehicle_plate_display"')
        self.assertContains(response, f'value="{self.vehicle.plate}"')
        self.assertContains(response, 'id="id_registered_vehicle_brand_display"')
        self.assertContains(response, f'value="{self.vehicle.brand}"')
        self.assertContains(response, 'id="id_registered_vehicle_engine_display"')
        self.assertContains(response, 'value="2.0"')
        self.assertContains(response, 'id="id_registered_vehicle_fuel_display"')
        self.assertContains(response, 'value="Gasolina"')

    def test_move_endpoint_reverts_on_overlap_conflict(self) -> None:
        base_start = timezone.now().replace(minute=0, second=0, microsecond=0)
        first = Appointment.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.vehicle,
            title="Primeiro",
            starts_at=base_start,
            ends_at=base_start + timedelta(hours=1),
        )
        second = Appointment.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.vehicle,
            title="Segundo",
            starts_at=base_start + timedelta(hours=2),
            ends_at=base_start + timedelta(hours=3),
        )

        response = self.client.post(
            reverse("scheduling:appointment_move", kwargs={"pk": second.pk}),
            {
                "starts_at": (base_start + timedelta(minutes=30)).isoformat(),
                "ends_at": (base_start + timedelta(hours=1, minutes=30)).isoformat(),
            },
        )

        second.refresh_from_db()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(second.starts_at, base_start + timedelta(hours=2))
        self.assertEqual(second.ends_at, base_start + timedelta(hours=3))
        self.assertTrue(Appointment.objects.filter(pk=first.pk).exists())


class CustomerPlateLookupTests(TestCase):
    def test_check_plate_endpoint_returns_vehicle_fields_used_in_scheduling(self) -> None:
        with patch(
            "apps.customer.views.fetch_vehicle_data",
            return_value={
                "brand": "FIAT",
                "model": "ARGO",
                "year_fabrication": "2023",
                "year_model": "2024",
                "fuel": "FLEX",
                "engine": "1.3 FLEX",
            },
        ):
            response = self.client.get(reverse("customer:check-plate", kwargs={"plate": "ABC1D23"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "brand": "FIAT",
                "model": "ARGO",
                "year_fabrication": "2023",
                "year_model": "2024",
                "fuel": "Flex",
                "engine": "1.3",
            },
        )
