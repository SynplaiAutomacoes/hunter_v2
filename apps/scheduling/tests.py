from __future__ import annotations

from datetime import timedelta

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
        self.assertIn("guest_customer_phone", exc_info.exception.message_dict)


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
                "guest_customer_name": "Cliente Balcao",
                "guest_customer_phone": "+5511999990000",
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
        self.assertEqual(appointment.guest_customer_name, "Cliente Balcao")
        self.assertEqual(str(appointment.guest_customer_phone), "(11) 99999-0000")

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
        self.assertEqual(response.headers.get("HX-Redirect"), f"{reverse('budget:budget_create')}?customer={self.customer.pk}")

    def test_save_and_create_budget_without_registered_customer_redirects_empty_budget(self) -> None:
        starts_at = timezone.now().replace(minute=0, second=0, microsecond=0)
        response = self.client.post(
            reverse("scheduling:appointment_create"),
            {
                "title": "Agendamento avulso",
                "guest_customer_name": "Cliente Balcao",
                "guest_customer_phone": "+5511999990000",
                "starts_at": starts_at.strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (starts_at + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "block_color": "#0ea5e9",
                "status": "scheduled",
                "action": "save_and_create_budget",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers.get("HX-Redirect"), reverse("budget:budget_create"))

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
