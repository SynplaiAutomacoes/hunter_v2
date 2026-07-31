from __future__ import annotations

from datetime import date

from django.test import TestCase

from apps.budget.models import Budget
from apps.customer.models import Customer, Vehicle
from apps.scheduling.forms import AppointmentCalendarFilterForm, AppointmentForm
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

    def test_form_does_not_eagerly_load_all_budget_and_workorder_choices_without_vehicle(self) -> None:
        form = AppointmentForm(workshop=self.workshop)

        self.assertFalse(form.fields["customer"].queryset.exists())
        self.assertFalse(form.fields["budget"].queryset.exists())
        self.assertFalse(form.fields["workorder"].queryset.exists())

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

        self.assertFalse(form.fields["customer"].queryset.exists())
