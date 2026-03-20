from __future__ import annotations

from datetime import datetime, timedelta
from typing import cast

from django import forms
from django.db.models import QuerySet
from django.http import QueryDict
from django.test.client import RequestFactory
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account, User
from apps.budget.forms import BudgetStep1Form
from apps.collaborators.models import WorkshopMember
from apps.customer.models import Customer, Vehicle
from apps.iam.utils import get_or_create_director_role
from apps.scheduling.forms import AppointmentCalendarFilterForm
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
    def test_allows_appointment_without_vehicle(self) -> None:
        _, workshop = create_director_user_with_workshop(suffix=9)
        customer = create_customer(workshop=workshop, suffix=9)
        starts_at = timezone.now().replace(minute=0, second=0, microsecond=0)

        appointment = Appointment(
            workshop=workshop,
            customer=customer,
            title="Sem veiculo",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )

        appointment.full_clean()

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

    def test_create_modal_prefills_aware_querystring_in_local_time(self) -> None:
        response = self.client.get(
            reverse("scheduling:appointment_create"),
            {
                "starts_at": "2026-03-20T14:00:00-03:00",
                "ends_at": "2026-03-20T15:00:00-03:00",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="2026-03-20T14:00"', html=False)
        self.assertContains(response, 'value="2026-03-20T15:00"', html=False)

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

    def test_events_endpoint_filters_by_customer_vehicle_pair(self) -> None:
        base_start = timezone.now().replace(minute=0, second=0, microsecond=0)
        Appointment.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.vehicle,
            title="Cliente 30",
            starts_at=base_start,
            ends_at=base_start + timedelta(hours=1),
        )

        other_customer = create_customer(workshop=self.workshop, suffix=33)
        other_vehicle = create_vehicle(workshop=self.workshop, customer=other_customer, suffix=33)
        Appointment.objects.create(
            workshop=self.workshop,
            customer=other_customer,
            vehicle=other_vehicle,
            title="Cliente 33",
            starts_at=base_start,
            ends_at=base_start + timedelta(hours=1),
        )

        response = self.client.get(
            reverse("scheduling:appointment_events"),
            {
                "start": base_start.isoformat(),
                "end": (base_start + timedelta(days=1)).isoformat(),
                "customer": str(self.customer.pk),
                "vehicle": str(self.vehicle.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["title"], "Cliente 30 - Cliente Agenda 30")

    def test_events_endpoint_serializes_times_in_local_timezone(self) -> None:
        local_tz = timezone.get_default_timezone()
        starts_at = timezone.make_aware(datetime(2026, 3, 20, 16, 0, 0), local_tz)
        Appointment.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.vehicle,
            title="Horario Local",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
        )

        response = self.client.get(
            reverse("scheduling:appointment_events"),
            {
                "start": starts_at.isoformat(),
                "end": (starts_at + timedelta(days=1)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["start"], starts_at.isoformat())
        self.assertEqual(payload[0]["end"], (starts_at + timedelta(hours=1)).isoformat())

    def test_move_endpoint_accepts_local_wall_datetime_strings(self) -> None:
        base_start = timezone.make_aware(datetime(2026, 3, 20, 16, 0, 0), timezone.get_default_timezone())
        appointment = Appointment.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.vehicle,
            title="Mover horario",
            starts_at=base_start,
            ends_at=base_start + timedelta(hours=1),
        )

        response = self.client.post(
            reverse("scheduling:appointment_move", kwargs={"pk": appointment.pk}),
            {
                "starts_at": "2026-03-20T17:00:00",
                "ends_at": "2026-03-20T18:00:00",
            },
        )

        appointment.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(timezone.localtime(appointment.starts_at), timezone.make_aware(datetime(2026, 3, 20, 17, 0, 0), timezone.get_default_timezone()))
        self.assertEqual(timezone.localtime(appointment.ends_at), timezone.make_aware(datetime(2026, 3, 20, 18, 0, 0), timezone.get_default_timezone()))


class BudgetStep1FormTests(TestCase):
    def test_prefills_vehicle_from_querystring_without_saved_instance(self) -> None:
        user, workshop = create_director_user_with_workshop(suffix=40)
        customer = create_customer(workshop=workshop, suffix=40)
        vehicle = create_vehicle(workshop=workshop, customer=customer, suffix=40)

        request = type("Request", (), {})()
        request_factory = RequestFactory()
        request = request_factory.get("/budget/create/", QueryDict(f"customer={customer.pk}&vehicle={vehicle.pk}"))
        request.user = user

        form = BudgetStep1Form(workshop=workshop, request=request)
        vehicle_field = cast(forms.ModelChoiceField, form.fields["vehicle"])
        vehicle_queryset = cast(QuerySet[Vehicle], vehicle_field.queryset)

        self.assertEqual(form.initial["customer"], customer.pk)
        self.assertEqual(form.initial["vehicle"], vehicle.pk)
        self.assertIn(vehicle, vehicle_queryset)


class AppointmentCalendarFilterFormTests(TestCase):
    def test_vehicle_filter_starts_disabled_without_customer(self) -> None:
        _, workshop = create_director_user_with_workshop(suffix=50)

        form = AppointmentCalendarFilterForm(workshop=workshop)
        vehicle_field = cast(forms.ModelChoiceField, form.fields["vehicle"])
        vehicle_queryset = cast(QuerySet[Vehicle], vehicle_field.queryset)

        self.assertTrue(vehicle_field.widget.attrs.get("disabled"))
        self.assertEqual(vehicle_queryset.count(), 0)

    def test_vehicle_filter_enables_and_loads_customer_vehicles(self) -> None:
        _, workshop = create_director_user_with_workshop(suffix=51)
        customer = create_customer(workshop=workshop, suffix=51)
        vehicle = create_vehicle(workshop=workshop, customer=customer, suffix=51)

        form = AppointmentCalendarFilterForm(data={"customer": str(customer.pk)}, workshop=workshop)
        vehicle_field = cast(forms.ModelChoiceField, form.fields["vehicle"])
        vehicle_queryset = cast(QuerySet[Vehicle], vehicle_field.queryset)

        self.assertNotIn("disabled", vehicle_field.widget.attrs)
        self.assertIn(vehicle, vehicle_queryset)
