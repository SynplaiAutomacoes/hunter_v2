from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.budget.models import Budget
from apps.customer.models import Customer, Vehicle
from apps.customer.vehicle_fuel import VehicleFuel
from apps.scheduling.forms import AppointmentCalendarFilterForm, AppointmentForm, default_appointment_ends_at
from apps.scheduling.models import Appointment, AppointmentStatus
from apps.workorder.models import WorkOrder
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Scheduling {suffix}",
        cnpj=f"52.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


def create_customer(*, workshop: Workshop, suffix: int) -> Customer:
    return Customer.objects.create(
        workshop=workshop,
        name=f"Cliente {suffix}",
        cpf_or_cnpj=f"1234567890{suffix:02d}",
        email=f"cliente{suffix}@example.com",
    )


def create_vehicle(*, workshop: Workshop, customer: Customer, suffix: int) -> Vehicle:
    return Vehicle.objects.create(
        workshop=workshop,
        customer=customer,
        plate=f"ABC1D{suffix:02d}",
        brand="Fiat",
        model=f"Modelo {suffix}",
        year_fabrication="2024",
        year_model="2025",
        color="Prata",
    )


class AppointmentFormChoiceLoadingTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=1)
        self.customer = create_customer(workshop=self.workshop, suffix=1)
        self.other_customer = create_customer(workshop=self.workshop, suffix=2)
        self.vehicle = create_vehicle(workshop=self.workshop, customer=self.customer, suffix=1)
        self.other_vehicle = create_vehicle(workshop=self.workshop, customer=self.other_customer, suffix=2)
        self.budget = Budget.objects.create(workshop=self.workshop, customer=self.customer, vehicle=self.vehicle, entry_date=date(2026, 7, 6))
        self.other_budget = Budget.objects.create(workshop=self.workshop, customer=self.other_customer, vehicle=self.other_vehicle, entry_date=date(2026, 7, 6))
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget)
        self.other_workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.other_budget)

    def test_new_form_defaults_alert_customer_and_lead_times(self) -> None:
        form = AppointmentForm(workshop=self.workshop)

        self.assertEqual(form.fields["alert_lead_times"].initial, ["60", "1440", "2880"])
        self.assertTrue(form.fields["alert_customer"].initial)
        shell_attrs = form.helper.layout.fields[-1].flat_attrs
        self.assertIn("&quot;alertCustomer&quot;: true", shell_attrs)

    def test_form_limits_budget_and_workorder_choices_to_selected_vehicle(self) -> None:
        form = AppointmentForm(
            workshop=self.workshop,
            initial={
                "customer": self.customer.pk,
                "vehicle": self.vehicle.pk,
                "budget": self.budget.pk,
                "workorder": self.workorder.pk,
            },
        )

        self.assertQuerySetEqual(form.fields["budget"].queryset.order_by("pk"), [self.budget], transform=lambda value: value)
        self.assertQuerySetEqual(form.fields["workorder"].queryset.order_by("pk"), [self.workorder], transform=lambda value: value)

    def test_calendar_filter_form_does_not_eagerly_load_all_customers(self) -> None:
        form = AppointmentCalendarFilterForm(workshop=self.workshop)
        self.assertEqual(form.fields["customer"].queryset.count(), 0)
        self.assertFalse(form.fields["customer"].queryset.exists())

    def test_guest_vehicle_fuel_falls_back_to_full_choices_without_fipe_cache(self) -> None:
        form = AppointmentForm(
            workshop=self.workshop,
            initial={
                "guest_vehicle_brand": "Marca Inexistente",
                "guest_vehicle_model": "Modelo Inexistente",
            },
        )

        fuel_choices = [value for value, _label in form.fields["guest_vehicle_fuel"].widget.choices if value]

        self.assertIn(VehicleFuel.GASOLINA, fuel_choices)
        self.assertIn(VehicleFuel.FLEX, fuel_choices)
        self.assertGreater(len(fuel_choices), 1)

    def test_guest_mode_requires_only_name_phone_and_plate(self) -> None:
        form = AppointmentForm(
            data={
                "is_customer_registered": "",
                "title": "Revisao guest",
                "guest_customer_name": "Joao Guest",
                "guest_customer_phone": "+5511988887777",
                "guest_vehicle_plate": "XYZ1A23",
                "starts_at": "2026-08-10T10:00",
                "ends_at": "2026-08-10T18:00",
                "status": AppointmentStatus.SCHEDULED,
                "alert_customer": "",
                "block_color": "#0ea5e9",
            },
            workshop=self.workshop,
        )
        self.assertTrue(form.is_valid(), form.errors)
        appointment = form.save()
        self.assertIsNone(appointment.customer_id)
        self.assertEqual(appointment.guest_customer_name, "JOAO GUEST")
        self.assertEqual(appointment.guest_vehicle_plate, "XYZ1A23")

    def test_guest_mode_rejects_missing_required_fields(self) -> None:
        form = AppointmentForm(
            data={
                "is_customer_registered": "",
                "title": "Revisao guest",
                "guest_customer_name": "",
                "guest_customer_phone": "",
                "guest_vehicle_plate": "",
                "starts_at": "2026-08-10T10:00",
                "ends_at": "2026-08-10T18:00",
                "status": AppointmentStatus.SCHEDULED,
                "alert_customer": "",
                "block_color": "#0ea5e9",
            },
            workshop=self.workshop,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("guest_customer_name", form.errors)
        self.assertIn("guest_customer_phone", form.errors)
        self.assertIn("guest_vehicle_plate", form.errors)


class AppointmentDefaultEndsAtTests(TestCase):
    def test_default_ends_at_is_1800_same_day(self) -> None:
        tz = ZoneInfo("America/Sao_Paulo")
        starts = timezone.make_aware(datetime(2026, 8, 10, 10, 30), tz)
        ends = default_appointment_ends_at(starts)
        local_ends = timezone.localtime(ends, tz)
        self.assertEqual(local_ends.hour, 18)
        self.assertEqual(local_ends.minute, 0)
        self.assertEqual(local_ends.date(), starts.date())

    def test_default_ends_at_falls_back_to_plus_one_hour_after_1800(self) -> None:
        tz = ZoneInfo("America/Sao_Paulo")
        starts = timezone.make_aware(datetime(2026, 8, 10, 18, 30), tz)
        ends = default_appointment_ends_at(starts)
        self.assertEqual(ends, starts + timedelta(hours=1))

    def test_default_ends_at_accepts_naive_wall_datetime(self) -> None:
        starts = datetime(2026, 8, 2, 21, 0)
        ends = default_appointment_ends_at(starts)
        self.assertTrue(timezone.is_naive(ends))
        self.assertEqual(ends, datetime(2026, 8, 2, 22, 0))


class AppointmentGuestModelValidationTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=9)

    def test_guest_clean_allows_optional_vehicle_details(self) -> None:
        starts = timezone.now() + timedelta(hours=2)
        appointment = Appointment(
            workshop=self.workshop,
            guest_customer_name="Ana Guest",
            guest_customer_phone="+5511999991111",
            guest_vehicle_plate="AAA1B23",
            title="Sem detalhes",
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            status=AppointmentStatus.SCHEDULED,
        )
        appointment.full_clean()

    def test_guest_clean_requires_name_phone_plate(self) -> None:
        starts = timezone.now() + timedelta(hours=2)
        appointment = Appointment(
            workshop=self.workshop,
            title="Incompleto",
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            status=AppointmentStatus.SCHEDULED,
        )
        with self.assertRaises(ValidationError) as ctx:
            appointment.full_clean()
        self.assertIn("guest_customer_name", ctx.exception.message_dict)
        self.assertIn("guest_customer_phone", ctx.exception.message_dict)
        self.assertIn("guest_vehicle_plate", ctx.exception.message_dict)
