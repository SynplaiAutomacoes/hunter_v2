from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import cast
from urllib.parse import urlparse
from unittest.mock import ANY, Mock, PropertyMock, patch

import requests
from django import forms
from django.http import QueryDict
from django.template import Context, Template
from django.template.loader import render_to_string

from apps.accounts.models import Account, User
from apps.budget.approval import approve_budget_with_stock
from django.http import Http404, HttpResponse
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.budget.forms import BudgetStep1Form, BudgetStep4Form, BudgetStep6Form
from apps.budget.forms.step_forms import BudgetStep3Form
from apps.budget.forms.shared import _render_budget_items_rows
from apps.budget.models import Budget, BudgetHistory, BudgetItem, BudgetKitItemOverride, BudgetStatus, BudgetType, SignatureStatus
from apps.budget.pdf_context import build_budget_pdf_context
from apps.budget.service import (
    BUDGET_SIGNATURE_DOCUMENT_ID_KEY,
    BUDGET_SIGNATURE_TOKEN_SALT,
    SuperSignError,
    build_signature_file_url,
    build_signature_payload,
    build_signature_preview_url,
    send_budget_for_signature,
)
from apps.checklist.models import Checklist, ChecklistItem
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit, KitApplication, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.documents.contract import DocumentPayload, SignatureDeliveryResult
from apps.core.documents.signature import normalize_signature_phone_number, parse_document_signature_token
from apps.core.documents.services import SignatureDeliveryServiceError, get_signed_document_url
from apps.core.text_normalization import sentence_case
from apps.collaborators.models import WorkshopCollaborator
from apps.core.query_filters import apply_query_param_filters
from apps.customer.models import Customer, Vehicle
from apps.collaborators.models import WorkshopMember
from apps.collaborators.services import freeze_existing_pricing_history, sync_current_month_salary_costs
from apps.iam.utils import get_or_create_director_role
from apps.stock.models import StockProduct
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.budget.views.pdf_views import signature_file, signature_preview, visualizar_pdf_assinatura
from apps.budget.views.workflow_views import BUDGET_LIST_FILTERS, BudgetCreateView, trigger_signature_send_if_needed
from apps.workshops.models.workshops import Workshop
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.util.monthly_costs import ADMIN_SALARY_MONTHLY_COST_NAME, MECHANIC_SALARY_MONTHLY_COST_NAME
from apps.workshops.services.files import StoredWorkshopFile
from apps.scheduling.models import Appointment


BUDGET_TEST_DEFAULTS_PREPARED = False


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Budget {suffix}",
        cnpj=f"11.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


def create_budget(*, workshop: Workshop) -> Budget:
    global BUDGET_TEST_DEFAULTS_PREPARED

    if not BUDGET_TEST_DEFAULTS_PREPARED:
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE budget_budget ALTER COLUMN discount_percentage SET DEFAULT 0")
        BUDGET_TEST_DEFAULTS_PREPARED = True

    now = timezone.now().replace(second=0, microsecond=0)
    budget = Budget(
        workshop=workshop,
        entry_date=now.date(),
        customer_agreed_departure_at=now + timedelta(days=2),
        service_expected_completion_at=now + timedelta(days=1),
    )
    budget.save()
    return budget


def create_director_user_with_workshop(*, suffix: int = 1) -> tuple[User, Workshop]:
    user = User.objects.create_user(username=f"budget-director{suffix}", password="123", cpf=f"12345678{suffix:03d}")
    account = Account.objects.create(name=f"Conta Budget {suffix}", owner=user)
    user.account = account
    user.is_account_owner = True
    user.save(update_fields=["account", "is_account_owner"])

    workshop = Workshop.objects.create(
        account=account,
        name=f"Oficina Diretor Budget {suffix}",
        cnpj=f"11.555.666/0001-{suffix:02d}",
        phone="+5511966666666",
        address="Rua Diretor Budget, 123",
    )

    director_role = get_or_create_director_role(account=account, with_all_permissions=True)
    WorkshopMember.objects.create(user=user, workshop=workshop, role=director_role, is_active=True)
    return user, workshop


def create_customer(*, workshop: Workshop, suffix: int = 1, phone: str = "+5511999999999") -> Customer:
    return Customer.objects.create(
        workshop=workshop,
        name=f"Cliente {suffix}",
        cpf_or_cnpj=f"123.456.789-{suffix:02d}",
        email=f"cliente{suffix}@example.com",
        phone=phone,
    )


def create_vehicle(
    *,
    workshop: Workshop,
    customer: Customer,
    suffix: int = 1,
    plate: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    year_fabrication: str = "2024",
    year_model: str = "2024",
    engine: str = "2.0",
    fuel: str = "Diesel",
) -> Vehicle:
    return Vehicle.objects.create(
        workshop=workshop,
        customer=customer,
        plate=plate or f"ABC1D{suffix:02d}",
        brand=brand or f"Marca {suffix}",
        model=model or f"Modelo {suffix}",
        year_fabrication=year_fabrication,
        year_model=year_model,
        color="Prata",
        engine=engine,
        fuel=fuel,
    )


def create_collaborator(*, workshop: Workshop, suffix: int = 1, name: str | None = None) -> WorkshopCollaborator:
    return WorkshopCollaborator.objects.create(
        workshop=workshop,
        name=name or f"Colaborador {suffix}",
        cpf=f"123456789{suffix:02d}",
        birth_date=timezone.now().date(),
        salary=Money("0.00", "BRL"),
        admission_date=timezone.now().date(),
        collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
    )


def create_salary_monthly_costs(*, workshop: Workshop) -> tuple[MonthlyCost, MonthlyCost]:
    productive_cost, _ = MonthlyCost.objects.get_or_create(workshop=workshop, name=MECHANIC_SALARY_MONTHLY_COST_NAME, defaults={"is_active": True})
    administrative_cost, _ = MonthlyCost.objects.get_or_create(workshop=workshop, name=ADMIN_SALARY_MONTHLY_COST_NAME, defaults={"is_active": True})
    return productive_cost, administrative_cost


def create_product(*, workshop: Workshop, suffix: int = 1, application: str = "") -> Product:
    group = CatalogGroup.objects.create(workshop=workshop, name=f"Grupo {suffix}")
    return Product.objects.create(
        workshop=workshop,
        code=f"P-{suffix:03d}",
        unit=Product.Unit.UND,
        name=f"Produto {suffix}",
        description=f"Descricao {suffix}",
        ncm="87089990",
        application=application,
        group=group,
        cost_price=Money("10.00", "BRL"),
        selling_price=Money("15.00", "BRL"),
    )


def create_service(*, workshop: Workshop, suffix: int = 1) -> Service:
    return Service.objects.create(
        workshop=workshop,
        name=f"Servico {suffix}",
        duration=timedelta(hours=1),
        suggested_cost=Money("5.00", "BRL"),
        selling_price=Money("20.00", "BRL"),
    )


def create_kit(*, workshop: Workshop, suffix: int, products: list[tuple[Product, int]], applications: list[dict[str, str | int]] | None = None) -> Kit:
    kit = Kit.objects.create(workshop=workshop, name=f"Kit {suffix}")
    for product, quantity in products:
        KitProduct.objects.create(kit=kit, product=product, quantity=quantity)
    for application in applications or []:
        KitApplication.objects.create(
            kit=kit,
            brand=str(application.get("brand", "")),
            model=str(application.get("model", "")),
            engine=str(application.get("engine", "")),
            fuel=str(application.get("fuel", "")),
            year_start=int(application.get("year_start", 0)),
            year_end=int(application.get("year_end", 0)),
        )
    return kit


def extract_token_from_url(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1]


class BudgetStep1FormTests(TestCase):
    def test_prefills_vehicle_from_request_and_renders_vehicle_option(self) -> None:
        user, workshop = create_director_user_with_workshop(suffix=69)
        customer = create_customer(workshop=workshop, suffix=69)
        vehicle = create_vehicle(workshop=workshop, customer=customer, suffix=69, plate="BDG6969")

        request = RequestFactory().get(reverse("budget:budget_create"), {"customer": customer.pk, "vehicle": vehicle.pk})
        request.user = user

        form = BudgetStep1Form(workshop=workshop, request=request)
        vehicle_field = cast(forms.ModelChoiceField, form.fields["vehicle"])
        vehicle_queryset = vehicle_field.queryset

        self.assertEqual(form.initial["customer"], customer.pk)
        self.assertEqual(form.initial["vehicle"], vehicle.pk)
        self.assertIsNotNone(vehicle_queryset)
        assert vehicle_queryset is not None
        self.assertQuerySetEqual(vehicle_queryset.order_by("pk"), [vehicle], transform=lambda obj: obj)

        rendered_vehicle_field = str(form["vehicle"])
        self.assertIn(str(vehicle), rendered_vehicle_field)
        self.assertIn(reverse("budget:vehicle-detail"), rendered_vehicle_field)
        self.assertIn(':disabled="!customerId"', rendered_vehicle_field)

    def test_accepts_warranty_budget_toggle(self) -> None:
        user, workshop = create_director_user_with_workshop(suffix=67)
        customer = create_customer(workshop=workshop, suffix=67)
        vehicle = create_vehicle(workshop=workshop, customer=customer, suffix=67, plate="BDG6767")

        request = RequestFactory().post(reverse("budget:budget_create"))
        request.user = user

        form = BudgetStep1Form(
            data={
                "entry_date": timezone.now().date().isoformat(),
                "is_warranty_budget": "on",
                "customer": str(customer.pk),
                "vehicle": str(vehicle.pk),
                "current_km": "15000",
                "fuel_level": "5",
            },
            workshop=workshop,
            request=request,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertTrue(form.cleaned_data["is_warranty_budget"])

    def test_renders_solid_red_no_badge_for_warranty_toggle_when_unchecked(self) -> None:
        user, workshop = create_director_user_with_workshop(suffix=66)

        request = RequestFactory().get(reverse("budget:budget_create"))
        request.user = user

        form = BudgetStep1Form(workshop=workshop, request=request)
        form_html = Template("{% load crispy_forms_tags %}{% crispy form %}").render(Context({"form": form}))

        self.assertIn("O orçamento é de garantia?", form_html)
        self.assertIn("badge-error", form_html)
        self.assertIn(">Não</span>", form_html)

    def test_accepts_current_km_with_thousands_separator(self) -> None:
        user, workshop = create_director_user_with_workshop(suffix=68)
        customer = create_customer(workshop=workshop, suffix=68)
        vehicle = create_vehicle(workshop=workshop, customer=customer, suffix=68, plate="BDG6868")

        request = RequestFactory().post(reverse("budget:budget_create"))
        request.user = user

        form = BudgetStep1Form(
            data={
                "entry_date": timezone.now().date().isoformat(),
                "customer": str(customer.pk),
                "vehicle": str(vehicle.pk),
                "current_km": "15.000",
                "fuel_level": "5",
            },
            workshop=workshop,
            request=request,
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertEqual(form.cleaned_data["current_km"], 15000)


class BudgetStep3FormChecklistFilterTests(TestCase):
    def test_shows_only_diagnostic_checklists_for_selection(self) -> None:
        _, workshop = create_director_user_with_workshop(suffix=121)
        budget = create_budget(workshop=workshop)

        diagnostic_checklist = Checklist.objects.create(
            workshop=workshop,
            name="Checklist Diagnostico",
            checklist_type=Checklist.ChecklistType.AUTOMOTIVE_DIAGNOSTIC,
        )
        Checklist.objects.create(
            workshop=workshop,
            name="Checklist Interno",
            checklist_type=Checklist.ChecklistType.INTERNAL,
        )

        form = BudgetStep3Form(instance=budget, workshop=workshop)
        checklist_field = cast(forms.ModelChoiceField, form.fields["checklist"])
        checklist_queryset = checklist_field.queryset

        assert checklist_queryset is not None
        self.assertQuerySetEqual(checklist_queryset.order_by("pk"), [diagnostic_checklist], transform=lambda obj: obj)

    def test_keeps_current_non_diagnostic_checklist_visible_for_legacy_budget(self) -> None:
        _, workshop = create_director_user_with_workshop(suffix=122)
        budget = create_budget(workshop=workshop)

        diagnostic_checklist = Checklist.objects.create(
            workshop=workshop,
            name="Checklist Diagnostico",
            checklist_type=Checklist.ChecklistType.AUTOMOTIVE_DIAGNOSTIC,
        )
        internal_checklist = Checklist.objects.create(
            workshop=workshop,
            name="Checklist Interno",
            checklist_type=Checklist.ChecklistType.INTERNAL,
        )
        budget.checklist = internal_checklist
        budget.save(update_fields=["checklist"])

        form = BudgetStep3Form(instance=budget, workshop=workshop)
        checklist_field = cast(forms.ModelChoiceField, form.fields["checklist"])
        checklist_queryset = checklist_field.queryset

        assert checklist_queryset is not None
        self.assertQuerySetEqual(checklist_queryset.order_by("pk"), [diagnostic_checklist, internal_checklist], transform=lambda obj: obj)


class BudgetKitSelectionCompatibilityTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=50)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.customer = create_customer(workshop=self.workshop, suffix=50)
        self.vehicle = create_vehicle(
            workshop=self.workshop,
            customer=self.customer,
            suffix=50,
            plate="KIT0A50",
            brand="Jeep",
            model="Renegade",
            year_fabrication="2020",
            year_model="2020",
            engine="2.0",
            fuel="Diesel",
        )
        self.budget = create_budget(workshop=self.workshop)
        self.budget.customer = self.customer
        self.budget.vehicle = self.vehicle
        self.budget.save(update_fields=["customer", "vehicle"])

        self.compatible_kit = create_kit(
            workshop=self.workshop,
            suffix=501,
            products=[],
            applications=[
                {
                    "brand": "Jeep",
                    "model": "Renegade",
                    "engine": "2.0",
                    "fuel": "Diesel",
                    "year_start": 2015,
                    "year_end": 2021,
                }
            ],
        )
        self.no_application_kit = create_kit(workshop=self.workshop, suffix=502, products=[])
        self.incompatible_kit = create_kit(
            workshop=self.workshop,
            suffix=503,
            products=[],
            applications=[
                {
                    "brand": "Jeep",
                    "model": "Compass",
                    "engine": "2.0",
                    "fuel": "Diesel",
                    "year_start": 2015,
                    "year_end": 2021,
                }
            ],
        )

    def test_item_selection_modal_marks_hidden_kits_outside_vehicle_filter(self) -> None:
        response = self.client.get(reverse("budget:item_selection", kwargs={"budget_id": self.budget.pk, "item_type": "kit"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.compatible_kit.name)
        self.assertContains(response, self.no_application_kit.name)
        self.assertContains(response, self.incompatible_kit.name)
        self.assertContains(response, "Compatível")
        self.assertContains(response, "Sem aplicação")
        self.assertContains(response, "Incompatível")
        self.assertContains(response, "Exibir kits ocultos (2)")
        self.assertContains(response, 'data-hidden-by-kit-filter="true" style="display: none;"', count=2)
        self.assertNotContains(response, "Compatibilidade indeterminada: os kits exibidos coincidem")
        self.assertNotContains(response, "Compatibilidade indeterminada")

    def test_item_selection_modal_shows_partial_compatibility_badge_on_first_page(self) -> None:
        partial_kit = create_kit(
            workshop=self.workshop,
            suffix=504,
            products=[],
            applications=[
                {
                    "brand": "Jeep",
                    "model": "Renegade",
                    "engine": "1.8",
                    "fuel": "Diesel",
                    "year_start": 2015,
                    "year_end": 2021,
                }
            ],
        )

        response = self.client.get(reverse("budget:item_selection", kwargs={"budget_id": self.budget.pk, "item_type": "kit"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, partial_kit.name)
        self.assertContains(
            response,
            '<span class="badge badge-accent inline-flex items-center gap-1"><span class="tooltip tooltip-left z-50 shrink-0 cursor-help" data-tip="Kit com marca, modelo e ano compatíveis, mas com diferenças de motor ou combustível." title="Kit com marca, modelo e ano compatíveis, mas com diferenças de motor ou combustível." tabindex="0"><span class="material-icons" style="font-size: 14px; line-height: 1;">info</span></span>Compatibilidade Parcial</span>',
            count=1,
            html=True,
        )
        self.assertContains(response, "Exibir kits ocultos (2)")
        self.assertContains(response, 'data-hidden-by-kit-filter="true" style="display: none;"', count=2)
        self.assertNotContains(response, "Compatibilidade indeterminada: os kits exibidos coincidem")

    def test_item_selection_modal_shows_indeterminate_badge_when_vehicle_data_is_incomplete(self) -> None:
        incomplete_vehicle = create_vehicle(
            workshop=self.workshop,
            customer=self.customer,
            suffix=51,
            plate="KIT0A51",
            brand="Jeep",
            model="Renegade",
            year_fabrication="2020",
            year_model="2020",
            engine="",
            fuel="Diesel",
        )
        incomplete_budget = create_budget(workshop=self.workshop)
        incomplete_budget.customer = self.customer
        incomplete_budget.vehicle = incomplete_vehicle
        incomplete_budget.save(update_fields=["customer", "vehicle"])

        response = self.client.get(reverse("budget:item_selection", kwargs={"budget_id": incomplete_budget.pk, "item_type": "kit"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.compatible_kit.name)
        self.assertContains(response, self.incompatible_kit.name)
        self.assertContains(response, self.no_application_kit.name)
        self.assertContains(
            response,
            '<span class="badge badge-warning inline-flex items-center gap-1"><span class="tooltip tooltip-left z-50 shrink-0 cursor-help" data-tip="Compatibilidade indeterminada: os kits exibidos coincidem com os dados disponíveis do veículo, mas faltam estas informações para confirmar a aplicação completa: motor." title="Compatibilidade indeterminada: os kits exibidos coincidem com os dados disponíveis do veículo, mas faltam estas informações para confirmar a aplicação completa: motor." tabindex="0"><span class="material-icons" style="font-size: 14px; line-height: 1;">info</span></span>Compatibilidade indeterminada</span>',
            count=1,
            html=True,
        )
        self.assertNotContains(response, 'class="alert alert-info py-3"')
        self.assertContains(
            response,
            "Compatibilidade indeterminada: os kits exibidos coincidem com os dados disponíveis do veículo, mas faltam estas informações para confirmar a aplicação completa: motor.",
        )
        self.assertContains(response, "Nenhum kit compatível encontrado")
        self.assertContains(response, "Sem aplicação")
        self.assertContains(response, "Exibir kits ocultos (2)")
        self.assertContains(response, 'data-hidden-by-kit-filter="true" style="display: none;"', count=2)
        self.assertNotContains(response, "Filtro indisponível")

    def test_item_selection_modal_shows_warning_when_no_compatible_kits_exist(self) -> None:
        no_match_vehicle = create_vehicle(
            workshop=self.workshop,
            customer=self.customer,
            suffix=52,
            plate="KIT0A52",
            brand="Jeep",
            model="Wrangler",
            year_fabrication="2020",
            year_model="2020",
            engine="2.0",
            fuel="Diesel",
        )
        no_match_budget = create_budget(workshop=self.workshop)
        no_match_budget.customer = self.customer
        no_match_budget.vehicle = no_match_vehicle
        no_match_budget.save(update_fields=["customer", "vehicle"])

        response = self.client.get(reverse("budget:item_selection", kwargs={"budget_id": no_match_budget.pk, "item_type": "kit"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.compatible_kit.name)
        self.assertContains(response, self.incompatible_kit.name)
        self.assertContains(response, self.no_application_kit.name)
        self.assertContains(response, "Exibir kits ocultos (3)")
        self.assertContains(response, "Nenhum kit compatível encontrado")
        self.assertContains(response, 'data-hidden-by-kit-filter="true" style="display: none;"', count=3)
        self.assertNotContains(response, "Compatibilidade indeterminada: os kits exibidos coincidem")
        self.assertNotContains(response, "Compatível")

    def test_item_selection_modal_treats_multiword_model_as_different_vehicle(self) -> None:
        self.vehicle.brand = "Toyota"
        self.vehicle.model = "Corolla"
        self.vehicle.save(update_fields=["brand", "model"])

        corolla_kit = create_kit(
            workshop=self.workshop,
            suffix=505,
            products=[],
            applications=[
                {
                    "brand": "Toyota",
                    "model": "Corolla",
                    "engine": "2.0",
                    "fuel": "Diesel",
                    "year_start": 2015,
                    "year_end": 2021,
                }
            ],
        )
        corolla_cross_kit = create_kit(
            workshop=self.workshop,
            suffix=506,
            products=[],
            applications=[
                {
                    "brand": "Toyota",
                    "model": "Corolla Cross",
                    "engine": "2.0",
                    "fuel": "Diesel",
                    "year_start": 2015,
                    "year_end": 2021,
                }
            ],
        )

        response = self.client.get(reverse("budget:item_selection", kwargs={"budget_id": self.budget.pk, "item_type": "kit"}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, corolla_kit.name)
        self.assertContains(response, corolla_cross_kit.name)
        self.assertContains(response, '<span class="badge badge-success">Compatível</span>', count=1, html=True)
        self.assertContains(response, "Exibir kits ocultos (4)")
        self.assertContains(response, 'data-hidden-by-kit-filter="true" style="display: none;"', count=4)

    def test_add_items_batch_rejects_incompatible_kit_for_vehicle(self) -> None:
        response = self.client.post(
            reverse("budget:add_items_batch", kwargs={"budget_id": self.budget.pk, "item_type": "kit"}),
            {"selected_items": [str(self.incompatible_kit.pk)]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kit indisponível para este veículo")
        self.assertFalse(BudgetItem.objects.filter(budget=self.budget, kit=self.incompatible_kit).exists())

    def test_add_items_batch_allows_kit_without_applications_as_fallback(self) -> None:
        response = self.client.post(
            reverse("budget:add_items_batch", kwargs={"budget_id": self.budget.pk, "item_type": "kit"}),
            {"selected_items": [str(self.no_application_kit.pk)]},
        )

        self.assertIn(response.status_code, {200, 302})
        self.assertTrue(BudgetItem.objects.filter(budget=self.budget, kit=self.no_application_kit).exists())

    def test_add_items_batch_allows_partially_compatible_kit_for_vehicle(self) -> None:
        partial_kit = create_kit(
            workshop=self.workshop,
            suffix=504,
            products=[],
            applications=[
                {
                    "brand": "Jeep",
                    "model": "Renegade",
                    "engine": "1.8",
                    "fuel": "Diesel",
                    "year_start": 2015,
                    "year_end": 2021,
                }
            ],
        )

        response = self.client.post(
            reverse("budget:add_items_batch", kwargs={"budget_id": self.budget.pk, "item_type": "kit"}),
            {"selected_items": [str(partial_kit.pk)]},
        )

        self.assertIn(response.status_code, {200, 302})
        self.assertTrue(BudgetItem.objects.filter(budget=self.budget, kit=partial_kit).exists())


class BudgetCreateViewAppointmentSyncTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=91)
        self.customer = create_customer(workshop=self.workshop, suffix=91)
        self.vehicle = create_vehicle(workshop=self.workshop, customer=self.customer, suffix=91, plate="BDG9191")
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        today = timezone.now()
        WorkshopCost.objects.create(workshop=self.workshop, month=today.month, year=today.year, mechanic_quantity=1)

    def test_create_syncs_budget_back_to_originating_appointment(self) -> None:
        previous_budget = create_budget(workshop=self.workshop)
        previous_budget.customer = self.customer
        previous_budget.vehicle = self.vehicle
        previous_budget.save(update_fields=["customer", "vehicle"])
        previous_workorder = WorkOrder.objects.create(workshop=self.workshop, budget=previous_budget)

        appointment = Appointment.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.vehicle,
            title="Agendamento com orçamento",
            starts_at=timezone.now().replace(minute=0, second=0, microsecond=0),
            ends_at=timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1),
            budget=previous_budget,
            workorder=previous_workorder,
        )

        response = self.client.post(
            f"{reverse('budget:budget_create')}?step=1&appointment_id={appointment.pk}",
            {
                "entry_date": timezone.now().date().isoformat(),
                "customer": str(self.customer.pk),
                "vehicle": str(self.vehicle.pk),
                "current_km": "12000",
                "fuel_level": "5",
            },
        )

        appointment.refresh_from_db()
        budget = Budget.objects.exclude(pk=previous_budget.pk).get()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(appointment.budget, budget)
        self.assertIsNone(appointment.workorder)
        self.assertEqual(appointment.budget.customer, self.customer)
        self.assertEqual(response.headers.get("Location"), f"{reverse('budget:budget_create')}?step=2&pk={budget.pk}&appointment_id={appointment.pk}")

    def test_create_persists_warranty_budget_flag_from_step_1(self) -> None:
        response = self.client.post(
            f"{reverse('budget:budget_create')}?step=1",
            {
                "entry_date": timezone.now().date().isoformat(),
                "is_warranty_budget": "on",
                "customer": str(self.customer.pk),
                "vehicle": str(self.vehicle.pk),
                "current_km": "12000",
                "fuel_level": "5",
            },
        )

        budget = Budget.objects.get(workshop=self.workshop)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(budget.is_warranty_budget)
        self.assertEqual(response.headers.get("Location"), f"{reverse('budget:budget_create')}?step=2&pk={budget.pk}")


class BudgetListFiltersTests(TestCase):
    def test_budget_list_filters_support_client_vehicle_collaborator_and_status(self) -> None:
        workshop = create_workshop(suffix=70)

        matching_customer = create_customer(workshop=workshop, suffix=70)
        matching_vehicle = create_vehicle(workshop=workshop, customer=matching_customer, suffix=70, plate="ABC1234")
        matching_collaborator = create_collaborator(workshop=workshop, suffix=70, name="Joao Silva")
        matching_budget = create_budget(workshop=workshop)
        matching_budget.customer = matching_customer
        matching_budget.vehicle = matching_vehicle
        matching_budget.collaborator = matching_collaborator
        matching_budget.status = BudgetStatus.APPROVED
        matching_budget.save(update_fields=["customer", "vehicle", "collaborator", "status"])
        matching_created_at = (timezone.now() - timedelta(days=3)).replace(hour=12, minute=0, second=0, microsecond=0)
        Budget.objects.filter(pk=matching_budget.pk).update(criado_em=matching_created_at)

        other_customer = create_customer(workshop=workshop, suffix=71)
        other_vehicle = create_vehicle(workshop=workshop, customer=other_customer, suffix=71, plate="XYZ9876")
        other_collaborator = create_collaborator(workshop=workshop, suffix=71, name="Maria Souza")
        other_budget = create_budget(workshop=workshop)
        other_budget.customer = other_customer
        other_budget.vehicle = other_vehicle
        other_budget.status = BudgetStatus.CANCELLED
        other_budget.save(update_fields=["customer", "vehicle", "status"])
        other_budget.collaborators.set([other_collaborator])
        Budget.objects.filter(pk=other_budget.pk).update(criado_em=timezone.now() - timedelta(days=12))

        selected_date = matching_created_at.date().isoformat()
        params = QueryDict(f"client=Cliente+70&vehicle=ABC1234&collaborator=Joao&status=approved&data_inicial={selected_date}&data_final={selected_date}")

        filtered = apply_query_param_filters(
            Budget.objects.filter(workshop=workshop),
            params=params,
            filter_configs=BUDGET_LIST_FILTERS,
        )

        self.assertQuerySetEqual(filtered.order_by("pk"), [matching_budget], transform=lambda obj: obj)
        self.assertNotIn(other_budget, filtered)

    def test_budget_filter_fields_template_renders_new_inputs(self) -> None:
        request = RequestFactory().get(
            "/budget/",
            {"client": "Ana", "vehicle": "ABC1234", "collaborator": "Joao", "status": BudgetStatus.APPROVED, "data_inicial": "2026-03-01", "data_final": "2026-03-31"},
        )
        template = Template("{% include 'budget/partials/budget_filters_fields.html' %}")

        html = template.render(
            Context(
                {
                    "request": request,
                    "table_id": "budget-table",
                    "status_choices": Budget.status.field.choices,
                }
            )
        )

        self.assertIn('name="client"', html)
        self.assertIn('name="vehicle"', html)
        self.assertIn('name="collaborator"', html)
        self.assertIn('name="status"', html)
        self.assertIn('name="data_inicial"', html)
        self.assertIn('name="data_final"', html)
        self.assertIn('value="Ana"', html)
        self.assertIn('value="ABC1234"', html)
        self.assertIn('value="Joao"', html)
        self.assertIn('value="2026-03-01"', html)
        self.assertIn('value="2026-03-31"', html)

    def _login_with_active_workshop(self, *, suffix: int) -> Workshop:
        user, workshop = create_director_user_with_workshop(suffix=suffix)
        self.client.force_login(user)

        session = self.client.session
        session["active_workshop_id"] = workshop.pk
        session.save()
        return workshop

    def test_budget_list_hides_cancelled_by_default(self) -> None:
        workshop = self._login_with_active_workshop(suffix=72)
        approved_budget = create_budget(workshop=workshop)
        approved_budget.status = BudgetStatus.APPROVED
        approved_budget.save(update_fields=["status"])
        cancelled_budget = create_budget(workshop=workshop)
        cancelled_budget.status = BudgetStatus.CANCELLED
        cancelled_budget.save(update_fields=["status"])

        response = self.client.get(reverse("budget:budget_list"))

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["budget"].order_by("pk"), [approved_budget], transform=lambda obj: obj)
        self.assertNotIn(cancelled_budget, response.context["budget"])

    def test_budget_list_displays_warranty_budget_badges(self) -> None:
        workshop = self._login_with_active_workshop(suffix=81)
        warranty_budget = create_budget(workshop=workshop)
        warranty_budget.is_warranty_budget = True
        warranty_budget.save(update_fields=["is_warranty_budget"])
        regular_budget = create_budget(workshop=workshop)
        regular_budget.is_warranty_budget = False
        regular_budget.save(update_fields=["is_warranty_budget"])

        response = self.client.get(reverse("budget:budget_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(Budget.is_warranty_budget.field.verbose_name))
        self.assertContains(response, '<span class="badge badge-success badge-sm whitespace-nowrap">Sim</span>', html=True)
        self.assertContains(response, '<span class="badge badge-error badge-sm whitespace-nowrap">Não</span>', html=True)

    def test_budget_list_shows_cancelled_when_cancelled_filter_is_selected(self) -> None:
        workshop = self._login_with_active_workshop(suffix=73)
        approved_budget = create_budget(workshop=workshop)
        approved_budget.status = BudgetStatus.APPROVED
        approved_budget.save(update_fields=["status"])
        cancelled_budget = create_budget(workshop=workshop)
        cancelled_budget.status = BudgetStatus.CANCELLED
        cancelled_budget.save(update_fields=["status"])

        response = self.client.get(reverse("budget:budget_list"), {"status": BudgetStatus.CANCELLED})

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["budget"].order_by("pk"), [cancelled_budget], transform=lambda obj: obj)
        self.assertNotIn(approved_budget, response.context["budget"])

    def test_budget_list_keeps_cancelled_hidden_for_invalid_status_filter(self) -> None:
        workshop = self._login_with_active_workshop(suffix=74)
        approved_budget = create_budget(workshop=workshop)
        approved_budget.status = BudgetStatus.APPROVED
        approved_budget.save(update_fields=["status"])
        cancelled_budget = create_budget(workshop=workshop)
        cancelled_budget.status = BudgetStatus.CANCELLED
        cancelled_budget.save(update_fields=["status"])

        response = self.client.get(reverse("budget:budget_list"), {"status": "invalid-status"})

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["budget"].order_by("pk"), [approved_budget], transform=lambda obj: obj)
        self.assertNotIn(cancelled_budget, response.context["budget"])

    def test_budget_list_shows_status_report_for_selected_status(self) -> None:
        workshop = self._login_with_active_workshop(suffix=75)
        approved_budget = create_budget(workshop=workshop)
        approved_budget.status = BudgetStatus.APPROVED
        approved_budget.save(update_fields=["status"])
        matching_created_at = (timezone.now() - timedelta(days=2)).replace(hour=12, minute=0, second=0, microsecond=0)
        Budget.objects.filter(pk=approved_budget.pk).update(criado_em=matching_created_at)
        second_approved_budget = create_budget(workshop=workshop)
        second_approved_budget.status = BudgetStatus.APPROVED
        second_approved_budget.save(update_fields=["status"])
        Budget.objects.filter(pk=second_approved_budget.pk).update(criado_em=timezone.now() - timedelta(days=10))
        draft_budget = create_budget(workshop=workshop)
        draft_budget.status = BudgetStatus.DRAFT
        draft_budget.save(update_fields=["status"])
        Budget.objects.filter(pk=draft_budget.pk).update(criado_em=matching_created_at)

        selected_date = matching_created_at.date().isoformat()

        response = self.client.get(reverse("budget:budget_list"), {"status": BudgetStatus.APPROVED, "data_inicial": selected_date, "data_final": selected_date})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selection_report"]["count"], 1)
        self.assertContains(response, "Resumo da selecao")
        self.assertContains(response, "Aprovado")
        self.assertContains(response, "Valor total")
        self.assertContains(response, "Imprimir selecao em PDF")
        self.assertContains(response, f"{reverse('budget:status_report_pdf_preview')}?status={BudgetStatus.APPROVED}")
        self.assertContains(response, reverse("budget:status_report_pdf"))
        self.assertContains(response, "download=1")
        self.assertContains(response, f"data_inicial={selected_date}")
        self.assertContains(response, f"data_final={selected_date}")

    def test_budget_list_supports_multiple_statuses_and_budget_types(self) -> None:
        workshop = self._login_with_active_workshop(suffix=51)
        approved_budget = create_budget(workshop=workshop)
        approved_budget.status = BudgetStatus.APPROVED
        approved_budget.budget_type = BudgetType.SALE
        approved_budget.save(update_fields=["status", "budget_type"])

        draft_budget = create_budget(workshop=workshop)
        draft_budget.status = BudgetStatus.DRAFT
        draft_budget.budget_type = BudgetType.WARRANTY
        draft_budget.save(update_fields=["status", "budget_type"])

        rejected_budget = create_budget(workshop=workshop)
        rejected_budget.status = BudgetStatus.REJECTED
        rejected_budget.budget_type = BudgetType.COURTESY
        rejected_budget.save(update_fields=["status", "budget_type"])

        params = QueryDict(mutable=True)
        params.setlist("status", [BudgetStatus.APPROVED, BudgetStatus.DRAFT])
        params.setlist("budget_type", [BudgetType.SALE, BudgetType.WARRANTY])

        response = self.client.get(reverse("budget:budget_list"), params)

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["budget"].order_by("pk"), [approved_budget, draft_budget], transform=lambda obj: obj)
        self.assertNotIn(rejected_budget, response.context["budget"])
        self.assertEqual(response.context["selection_report"]["count"], 2)
        self.assertEqual(len(response.context["selection_report"]["badges"]), 4)

    def test_budget_list_collaborator_filter_deduplicates_rows_when_budget_matches_multiple_collaborators(self) -> None:
        workshop = self._login_with_active_workshop(suffix=58)

        duplicated_budget = create_budget(workshop=workshop)
        duplicated_budget.status = BudgetStatus.APPROVED
        duplicated_budget.save(update_fields=["status"])

        first_matching_collaborator = create_collaborator(workshop=workshop, suffix=5111, name="Ana Teste")
        second_matching_collaborator = create_collaborator(workshop=workshop, suffix=5112, name="Ana Souza")
        duplicated_budget.collaborators.set([first_matching_collaborator, second_matching_collaborator])

        non_matching_budget = create_budget(workshop=workshop)
        non_matching_budget.status = BudgetStatus.APPROVED
        non_matching_budget.save(update_fields=["status"])
        non_matching_collaborator = create_collaborator(workshop=workshop, suffix=5113, name="Carlos Silva")
        non_matching_budget.collaborators.set([non_matching_collaborator])

        response = self.client.get(reverse("budget:budget_list"), {"collaborator": "Ana"})

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["budget"], [duplicated_budget], transform=lambda obj: obj)
        self.assertNotIn(non_matching_budget, response.context["budget"])

    def test_budget_status_report_counts_only_selected_status(self) -> None:
        workshop = self._login_with_active_workshop(suffix=76)

        matching_customer = create_customer(workshop=workshop, suffix=76)
        matching_vehicle = create_vehicle(workshop=workshop, customer=matching_customer, suffix=76, plate="ABC7676")
        matching_collaborator = create_collaborator(workshop=workshop, suffix=76, name="Carlos 76")
        matching_budget = create_budget(workshop=workshop)
        matching_budget.customer = matching_customer
        matching_budget.vehicle = matching_vehicle
        matching_budget.collaborator = matching_collaborator
        matching_budget.status = BudgetStatus.APPROVED
        matching_budget.save(update_fields=["customer", "vehicle", "collaborator", "status"])
        matching_created_at = (timezone.now() - timedelta(days=3)).replace(hour=12, minute=0, second=0, microsecond=0)
        Budget.objects.filter(pk=matching_budget.pk).update(criado_em=matching_created_at)

        other_customer = create_customer(workshop=workshop, suffix=77)
        other_vehicle = create_vehicle(workshop=workshop, customer=other_customer, suffix=77, plate="ABC7777")
        other_collaborator = create_collaborator(workshop=workshop, suffix=77, name="Carlos 77")
        other_budget = create_budget(workshop=workshop)
        other_budget.customer = other_customer
        other_budget.vehicle = other_vehicle
        other_budget.collaborator = other_collaborator
        other_budget.status = BudgetStatus.APPROVED
        other_budget.save(update_fields=["customer", "vehicle", "collaborator", "status"])
        Budget.objects.filter(pk=other_budget.pk).update(criado_em=matching_created_at)

        out_of_range_budget = create_budget(workshop=workshop)
        out_of_range_budget.status = BudgetStatus.APPROVED
        out_of_range_budget.save(update_fields=["status"])
        Budget.objects.filter(pk=out_of_range_budget.pk).update(criado_em=timezone.now() - timedelta(days=14))

        draft_budget = create_budget(workshop=workshop)
        draft_budget.status = BudgetStatus.DRAFT
        draft_budget.save(update_fields=["status"])

        selected_date = matching_created_at.date().isoformat()
        response = self.client.get(
            reverse("budget:budget_list"),
            {"status": BudgetStatus.APPROVED, "client": matching_customer.name, "data_inicial": selected_date, "data_final": selected_date},
        )

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["budget"].order_by("pk"), [matching_budget], transform=lambda obj: obj)
        self.assertNotIn(other_budget, response.context["budget"])
        self.assertNotIn(out_of_range_budget, response.context["budget"])
        self.assertEqual(response.context["selection_report"]["count"], 1)

    def test_budget_list_hides_status_report_without_valid_status(self) -> None:
        workshop = self._login_with_active_workshop(suffix=78)
        approved_budget = create_budget(workshop=workshop)
        approved_budget.status = BudgetStatus.APPROVED
        approved_budget.save(update_fields=["status"])

        response = self.client.get(reverse("budget:budget_list"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["selection_report"])
        self.assertNotContains(response, "Resumo da selecao")
        self.assertNotContains(response, "Imprimir selecao em PDF")

    def test_budget_list_htmx_partial_keeps_status_report_in_table_content(self) -> None:
        workshop = self._login_with_active_workshop(suffix=79)
        approved_budget = create_budget(workshop=workshop)
        approved_budget.status = BudgetStatus.APPROVED
        approved_budget.save(update_fields=["status"])
        second_approved_budget = create_budget(workshop=workshop)
        second_approved_budget.status = BudgetStatus.APPROVED
        second_approved_budget.save(update_fields=["status"])

        response = self.client.get(reverse("budget:budget_list"), {"status": BudgetStatus.APPROVED}, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="budget-table-content"')
        self.assertContains(response, "Resumo da selecao")
        self.assertContains(response, "Aprovado")
        self.assertContains(response, "Imprimir selecao em PDF")


class BudgetStatusReportPdfTests(TestCase):
    def _login_with_active_workshop(self, *, suffix: int) -> Workshop:
        user, workshop = create_director_user_with_workshop(suffix=suffix)
        self.client.force_login(user)

        session = self.client.session
        session["active_workshop_id"] = workshop.pk
        session.save()
        return workshop

    def test_status_report_pdf_preview_renders_html_for_iframe(self) -> None:
        workshop = self._login_with_active_workshop(suffix=95)
        customer = create_customer(workshop=workshop, suffix=95)
        vehicle = create_vehicle(workshop=workshop, customer=customer, suffix=95, plate="BDG9595")
        collaborator = create_collaborator(workshop=workshop, suffix=95, name="Tecnico 95")

        approved_budget = create_budget(workshop=workshop)
        approved_budget.customer = customer
        approved_budget.vehicle = vehicle
        approved_budget.status = BudgetStatus.APPROVED
        approved_budget.save(update_fields=["customer", "vehicle", "status"])
        approved_budget.collaborators.set([collaborator])
        matching_created_at = (timezone.now() - timedelta(days=4)).replace(hour=12, minute=0, second=0, microsecond=0)
        Budget.objects.filter(pk=approved_budget.pk).update(criado_em=matching_created_at)

        other_customer = create_customer(workshop=workshop, suffix=951)
        other_vehicle = create_vehicle(workshop=workshop, customer=other_customer, suffix=951, plate="BDG9511")
        other_collaborator = create_collaborator(workshop=workshop, suffix=951, name="Tecnico 951")
        out_of_range_budget = create_budget(workshop=workshop)
        out_of_range_budget.customer = other_customer
        out_of_range_budget.vehicle = other_vehicle
        out_of_range_budget.status = BudgetStatus.APPROVED
        out_of_range_budget.save(update_fields=["customer", "vehicle", "status"])
        out_of_range_budget.collaborators.set([other_collaborator])
        Budget.objects.filter(pk=out_of_range_budget.pk).update(criado_em=timezone.now() - timedelta(days=12))

        draft_budget = create_budget(workshop=workshop)
        draft_budget.status = BudgetStatus.DRAFT
        draft_budget.save(update_fields=["status"])

        selected_date = matching_created_at.date().isoformat()

        response = self.client.get(reverse("budget:status_report_pdf_preview"), {"status": BudgetStatus.APPROVED, "data_inicial": selected_date, "data_final": selected_date})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<!DOCTYPE html>", html=False)
        self.assertContains(response, "Relatorio de Orcamentos Filtrados")
        self.assertContains(response, workshop.name)
        self.assertContains(response, "Aprovado")
        self.assertContains(response, customer.name)
        self.assertContains(response, vehicle.plate)
        self.assertContains(response, collaborator.name)
        self.assertNotContains(response, f"#{out_of_range_budget.pk}")
        self.assertContains(response, matching_created_at.strftime("%d/%m/%Y"))
        self.assertIsNone(response.headers.get("X-Frame-Options"))

    @patch("apps.budget.views.workflow_views.render_budget_status_report_pdf_document")
    def test_status_report_pdf_view_returns_attachment_with_filtered_selection(self, render_document_mock) -> None:
        workshop = self._login_with_active_workshop(suffix=96)

        matching_customer = create_customer(workshop=workshop, suffix=96)
        matching_vehicle = create_vehicle(workshop=workshop, customer=matching_customer, suffix=96, plate="BDG9696")
        matching_collaborator = create_collaborator(workshop=workshop, suffix=96, name="Tecnico 96")
        matching_budget = create_budget(workshop=workshop)
        matching_budget.customer = matching_customer
        matching_budget.vehicle = matching_vehicle
        matching_budget.collaborator = matching_collaborator
        matching_budget.status = BudgetStatus.APPROVED
        matching_budget.save(update_fields=["customer", "vehicle", "collaborator", "status"])
        matching_created_at = (timezone.now() - timedelta(days=5)).replace(hour=12, minute=0, second=0, microsecond=0)
        Budget.objects.filter(pk=matching_budget.pk).update(criado_em=matching_created_at)

        other_customer = create_customer(workshop=workshop, suffix=97)
        other_vehicle = create_vehicle(workshop=workshop, customer=other_customer, suffix=97, plate="BDG9797")
        other_collaborator = create_collaborator(workshop=workshop, suffix=97, name="Tecnico 97")
        other_budget = create_budget(workshop=workshop)
        other_budget.customer = other_customer
        other_budget.vehicle = other_vehicle
        other_budget.collaborator = other_collaborator
        other_budget.status = BudgetStatus.APPROVED
        other_budget.save(update_fields=["customer", "vehicle", "collaborator", "status"])
        Budget.objects.filter(pk=other_budget.pk).update(criado_em=matching_created_at)

        out_of_range_budget = create_budget(workshop=workshop)
        out_of_range_budget.status = BudgetStatus.APPROVED
        out_of_range_budget.save(update_fields=["status"])
        Budget.objects.filter(pk=out_of_range_budget.pk).update(criado_em=timezone.now() - timedelta(days=17))

        draft_budget = create_budget(workshop=workshop)
        draft_budget.status = BudgetStatus.DRAFT
        draft_budget.save(update_fields=["status"])

        render_document_mock.return_value = DocumentPayload(content=b"%PDF-budget-status-report", filename="relatorio_orcamentos_filtrados.pdf")
        selected_date = matching_created_at.date().isoformat()

        response = self.client.get(
            reverse("budget:status_report_pdf"),
            {"status": BudgetStatus.APPROVED, "client": matching_customer.name, "data_inicial": selected_date, "data_final": selected_date, "download": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-budget-status-report")
        self.assertIn('attachment; filename="relatorio_orcamentos_filtrados.pdf"', response["Content-Disposition"])

        context = render_document_mock.call_args.kwargs["context"]
        self.assertEqual(context["selection_report"]["count"], 1)
        self.assertCountEqual(context["report_budgets"], [matching_budget])
        self.assertNotIn(other_budget, context["report_budgets"])
        self.assertNotIn(out_of_range_budget, context["report_budgets"])
        self.assertEqual(context["status_report_pdf_title"], "Relatorio de Orcamentos Filtrados")
        self.assertEqual(context["status_report_period_label"], f"{matching_created_at.strftime('%d/%m/%Y')} a {matching_created_at.strftime('%d/%m/%Y')}")

    def test_status_report_pdf_views_return_404_without_valid_status(self) -> None:
        workshop = self._login_with_active_workshop(suffix=98)
        approved_budget = create_budget(workshop=workshop)
        approved_budget.status = BudgetStatus.APPROVED
        approved_budget.save(update_fields=["status"])

        preview_response = self.client.get(reverse("budget:status_report_pdf_preview"))
        pdf_response = self.client.get(reverse("budget:status_report_pdf"), {"status": "invalid-status"})

        self.assertEqual(preview_response.status_code, 404)
        self.assertEqual(pdf_response.status_code, 404)


class BudgetTotalsConsistencyTests(TestCase):
    def test_total_base_value_uses_item_selling_totals_only(self) -> None:
        workshop = create_workshop(suffix=71)
        budget = create_budget(workshop=workshop)

        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Peca local",
            quantity=2,
            product_cost_price=Money("50.00", "BRL"),
            product_selling_price=Money("100.00", "BRL"),
            shipping=Money("5.00", "BRL"),
        )
        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Servico local",
            quantity=1,
            service_cost_price=Money("0.00", "BRL"),
            service_selling_price=Money("0.01", "BRL"),
        )

        self.assertEqual(budget.total_products_value, Money("205.00", "BRL"))
        self.assertEqual(budget.total_services_value, Money("0.01", "BRL"))
        self.assertEqual(budget.total_base_value, Money("205.01", "BRL"))

    def test_total_budget_value_applies_discount_over_item_totals(self) -> None:
        workshop = create_workshop(suffix=72)
        budget = create_budget(workshop=workshop)

        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Servico local",
            quantity=1,
            service_selling_price=Money("0.01", "BRL"),
        )

        budget.discount_value = Money(Decimal("0.01"), "BRL")
        budget.save(update_fields=["discount_value"])

        self.assertEqual(budget.total_base_value, Money("0.01", "BRL"))
        self.assertEqual(budget.total_budget_value, Money("0.00", "BRL"))

    def test_discount_percentage_recomputes_discount_value_from_subtotal(self) -> None:
        workshop = create_workshop(suffix=73)
        budget = create_budget(workshop=workshop)

        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Servico percentual",
            quantity=1,
            service_selling_price=Money("200.00", "BRL"),
        )

        budget.discount_percentage = Decimal("0.15")
        budget.discount_value = Money("0.00", "BRL")
        budget.save(update_fields=["discount_percentage", "discount_value"])

        budget.refresh_from_db()
        self.assertEqual(budget.resolved_discount_value, Money("30.00", "BRL"))
        self.assertEqual(budget.discount_value, Money("30.00", "BRL"))
        self.assertEqual(budget.discount_percentage, Decimal("0.150000"))
        self.assertEqual(budget.total_budget_value, Money("170.00", "BRL"))

    def test_discount_value_recomputes_discount_percentage(self) -> None:
        workshop = create_workshop(suffix=74)
        budget = create_budget(workshop=workshop)

        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Servico valor",
            quantity=1,
            service_selling_price=Money("250.00", "BRL"),
        )

        budget.discount_value = Money("50.00", "BRL")
        budget.discount_percentage = Decimal("0")
        budget.save(update_fields=["discount_value", "discount_percentage"])

        budget.refresh_from_db()
        self.assertEqual(budget.discount_value, Money("50.00", "BRL"))
        self.assertEqual(budget.discount_percentage, Decimal("0.200000"))
        self.assertEqual(budget.total_budget_value, Money("200.00", "BRL"))

    def test_pricing_snapshot_uses_traditional_labor_value_when_traditional_method_is_selected(self) -> None:
        workshop = create_workshop(suffix=75)
        budget = create_budget(workshop=workshop)

        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Servico tradicional",
            quantity=1,
            service_cost_price=Money("40.00", "BRL"),
            service_selling_price=Money("100.00", "BRL"),
            duration=timedelta(hours=2),
        )

        with patch.object(Budget, "calculate_pricing_methods", return_value={"method_name": "Tradicional", "venda_mao_obra": Money("160.00", "BRL")}):
            snapshot = budget.pricing_snapshot

        self.assertEqual(snapshot.total_services_value, Money("100.00", "BRL"))
        self.assertEqual(snapshot.total_labor_selling_value, Money("160.00", "BRL"))
        self.assertEqual(snapshot.total_labor_by_slider, Money("160.00", "BRL"))
        self.assertEqual(budget.total_base_value, Money("160.00", "BRL"))

    def test_step4_summary_uses_selected_item_service_total_not_pricing_method_total(self) -> None:
        workshop = create_workshop(suffix=77)
        budget = create_budget(workshop=workshop)

        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Servico do kit",
            quantity=1,
            service_cost_price=Money("40.00", "BRL"),
            service_selling_price=Money("100.00", "BRL"),
            duration=timedelta(hours=2),
        )

        with patch.object(Budget, "calculate_pricing_methods", return_value={"method_name": "Tradicional", "venda_mao_obra": Money("160.00", "BRL")}):
            self.assertEqual(budget.display_total_services_by_slider, Money("160.00", "BRL"))
            self.assertEqual(budget.selected_items_total_services_value, Money("100.00", "BRL"))
            rendered_summary = render_to_string("budget/partials/components/budget_summary.html", {"budget": budget})

        self.assertIn("R$\xa0100,00", rendered_summary)
        self.assertNotIn("R$\xa0160,00", rendered_summary)

    def test_step4_summary_service_total_matches_single_kit_services_total(self) -> None:
        workshop = create_workshop(suffix=78)
        budget = create_budget(workshop=workshop)
        service = create_service(workshop=workshop, suffix=78)
        kit = create_kit(workshop=workshop, suffix=78, products=[])
        KitService.objects.create(kit=kit, service=service, quantity=2, duration=timedelta(hours=1), selling_price=Money("55.00", "BRL"))
        item = BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit, quantity=1)

        with patch.object(Budget, "calculate_pricing_methods", return_value={"method_name": "Tradicional", "venda_mao_obra": Money("160.00", "BRL")}):
            self.assertEqual(item.get_kit_services_total(), Money("110.00", "BRL"))
            self.assertEqual(budget.display_total_services_by_slider, Money("160.00", "BRL"))
            self.assertEqual(budget.selected_items_total_services_value, item.get_kit_services_total())

    def test_pricing_snapshot_keeps_hunter_labor_sum_when_hunter_method_is_selected(self) -> None:
        workshop = create_workshop(suffix=76)
        budget = create_budget(workshop=workshop)

        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Servico hunter",
            quantity=1,
            service_cost_price=Money("40.00", "BRL"),
            service_selling_price=Money("100.00", "BRL"),
            duration=timedelta(hours=2),
        )

        with patch.object(Budget, "calculate_pricing_methods", return_value={"method_name": "Hunter", "venda_mao_obra": Money("160.00", "BRL")}):
            snapshot = budget.pricing_snapshot

        self.assertEqual(snapshot.total_services_value, Money("100.00", "BRL"))
        self.assertEqual(snapshot.total_labor_selling_value, Money("100.00", "BRL"))
        self.assertEqual(snapshot.total_labor_by_slider, Money("100.00", "BRL"))
        self.assertEqual(budget.total_base_value, Money("100.00", "BRL"))

    def test_warranty_budget_display_totals_use_costs_without_changing_stored_sales(self) -> None:
        workshop = create_workshop(suffix=41)
        budget = create_budget(workshop=workshop)
        budget.is_warranty_budget = True
        budget.save(update_fields=["is_warranty_budget"])

        product_item = BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Peca garantia",
            quantity=2,
            product_cost_price=Money("50.00", "BRL"),
            product_selling_price=Money("100.00", "BRL"),
            shipping=Money("5.00", "BRL"),
        )
        service_item = BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Servico garantia",
            quantity=1,
            service_cost_price=Money("30.00", "BRL"),
            service_selling_price=Money("90.00", "BRL"),
        )
        budget.discount_value = Money("5.00", "BRL")

        product_item.refresh_from_db()
        service_item.refresh_from_db()

        self.assertEqual(product_item.product_selling_price, Money("100.00", "BRL"))
        self.assertEqual(service_item.service_selling_price, Money("90.00", "BRL"))
        self.assertEqual(budget.display_total_products_by_slider_without_shipping, Money("100.00", "BRL"))
        self.assertEqual(budget.display_total_services_by_slider, Money("30.00", "BRL"))
        self.assertEqual(budget.display_total_base_value, Money("135.00", "BRL"))
        self.assertEqual(budget.display_resolved_discount_value, Money("5.00", "BRL"))
        self.assertEqual(budget.display_total_budget_value, Money("130.00", "BRL"))


class BudgetDiscountUpdateViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=80)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_update_budget_discount_accepts_percentage_as_source_of_truth(self) -> None:
        budget = create_budget(workshop=self.workshop)
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            is_local=True,
            description="Servico percentual view",
            quantity=1,
            service_selling_price=Money("300.00", "BRL"),
        )

        response = self.client.post(
            reverse("budget:update_budget_discount", kwargs={"budget_id": budget.pk}),
            data={"discount_percentage": "0.10", "discount_value_0": "0.00"},
        )

        budget.refresh_from_db()
        self.assertEqual(response.status_code, 204)
        self.assertEqual(budget.discount_percentage, Decimal("0.100000"))
        self.assertEqual(budget.discount_value, Money("30.00", "BRL"))

    def test_update_budget_discount_recomputes_percentage_from_value(self) -> None:
        budget = create_budget(workshop=self.workshop)
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            is_local=True,
            description="Servico valor view",
            quantity=1,
            service_selling_price=Money("400.00", "BRL"),
        )

        response = self.client.post(
            reverse("budget:update_budget_discount", kwargs={"budget_id": budget.pk}),
            data={"discount_percentage": "0", "discount_value_0": "40.00"},
        )

        budget.refresh_from_db()
        self.assertEqual(response.status_code, 204)
        self.assertEqual(budget.discount_value, Money("40.00", "BRL"))
        self.assertEqual(budget.discount_percentage, Decimal("0.100000"))

    def test_update_budget_discount_syncs_workorder_when_budget_is_approved(self) -> None:
        budget = create_budget(workshop=self.workshop)
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            is_local=True,
            description="Servico com os",
            quantity=1,
            service_selling_price=Money("500.00", "BRL"),
        )
        budget.status = BudgetStatus.APPROVED
        budget.save(update_fields=["status"])

        workorder = WorkOrder.objects.get(budget=budget)
        response = self.client.post(
            reverse("budget:update_budget_discount", kwargs={"budget_id": budget.pk}),
            data={"discount_percentage": "0.10", "discount_value_0": "0.00"},
        )

        budget.refresh_from_db()
        workorder.refresh_from_db()

        self.assertEqual(response.status_code, 204)
        self.assertEqual(budget.discount_value, Money("50.00", "BRL"))
        self.assertEqual(workorder.discount_value, Money("50.00", "BRL"))


class BudgetSignaturePersistenceTests(TestCase):
    def test_mark_signature_sent_persists_envelope_and_document_id(self) -> None:
        workshop = create_workshop(suffix=73)
        budget = create_budget(workshop=workshop)

        budget.mark_signature_sent("env-123", document_id="doc-123")
        budget.refresh_from_db()

        self.assertEqual(budget.signature_external_id, "env-123")
        self.assertEqual(budget.signature_document_id, "doc-123")


class BudgetSignatureTokenUrlTests(TestCase):
    def test_build_signature_payload_uses_budget_specific_key(self) -> None:
        workshop = create_workshop(suffix=74)
        budget = create_budget(workshop=workshop)

        payload = build_signature_payload(budget)

        self.assertEqual(payload, {"budget_id": budget.id, "version": budget.signature_token_version})

    @override_settings(APP_BASE_URL="https://app.example.com")
    def test_build_signature_preview_url_generates_tokenized_budget_link(self) -> None:
        workshop = create_workshop(suffix=75)
        budget = create_budget(workshop=workshop)

        url = build_signature_preview_url(budget=budget)
        token = extract_token_from_url(url)

        payload = parse_document_signature_token(
            token=token,
            token_salt=BUDGET_SIGNATURE_TOKEN_SALT,
            document_id_key=BUDGET_SIGNATURE_DOCUMENT_ID_KEY,
        )

        self.assertEqual(payload.document_id, budget.id)
        self.assertEqual(payload.version, budget.signature_token_version)

    @override_settings(APP_BASE_URL="https://app.example.com")
    def test_build_signature_file_url_generates_tokenized_budget_link(self) -> None:
        workshop = create_workshop(suffix=76)
        budget = create_budget(workshop=workshop)

        url = build_signature_file_url(budget=budget)
        token = extract_token_from_url(url)

        payload = parse_document_signature_token(
            token=token,
            token_salt=BUDGET_SIGNATURE_TOKEN_SALT,
            document_id_key=BUDGET_SIGNATURE_DOCUMENT_ID_KEY,
        )

        self.assertEqual(payload.document_id, budget.id)
        self.assertEqual(payload.version, budget.signature_token_version)


class BudgetSignatureDeliveryTests(TestCase):
    @patch("apps.budget.service.send_document_for_signature")
    @patch("apps.budget.service.render_budget_pdf_document")
    def test_send_budget_for_signature_uses_core_payload_builders(self, render_pdf_mock, send_document_mock) -> None:
        workshop = create_workshop(suffix=77)
        budget = create_budget(workshop=workshop)
        customer = create_customer(workshop=workshop, suffix=77)
        budget.customer = customer
        budget.save(update_fields=["customer"])

        render_pdf_mock.return_value = DocumentPayload(content=b"budget-pdf", filename="orcamento.pdf")
        send_document_mock.return_value = SignatureDeliveryResult(
            envelope_id="env-77",
            document_id="doc-77",
            provider="supersign",
            raw_response={"ok": True},
        )

        result = send_budget_for_signature(budget=budget)

        self.assertEqual(result.envelope_id, "env-77")
        _, kwargs = send_document_mock.call_args
        self.assertEqual(kwargs["file_name"], f"orcamento-{budget.id}.pdf")
        self.assertEqual(kwargs["document_ref_id"], f"budget-{budget.id}")
        self.assertEqual(kwargs["signatory"]["id"], f"customer-{budget.id}")
        self.assertEqual(kwargs["signatory"]["authMethod"], "WHATSAPP")
        self.assertEqual(kwargs["signatory"]["phoneNumber"], normalize_signature_phone_number(customer.phone))
        self.assertEqual(kwargs["observers"][0]["email"], customer.email)
        self.assertEqual(kwargs["fields"][0]["documentId"], f"budget-{budget.id}")
        self.assertEqual(kwargs["fields"][0]["signatoryId"], f"customer-{budget.id}")
        self.assertEqual(kwargs["fields"][0]["pageNumber"], 1)


class BudgetPdfContextTests(TestCase):
    def test_build_budget_pdf_context_includes_product_application(self) -> None:
        workshop = create_workshop(suffix=82)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=82, application="Fiat Uno")

        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            product=product,
            quantity=1,
        )

        context = build_budget_pdf_context(budget=budget, observacao="Observacao de teste")

        self.assertEqual(context["produtos"][0]["application"], "Fiat Uno")

    def test_build_budget_pdf_context_includes_customer_supplied_flag(self) -> None:
        workshop = create_workshop(suffix=83)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=83)

        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            product=product,
            quantity=1,
            is_customer_supplied=True,
        )

        context = build_budget_pdf_context(budget=budget, observacao="Observacao de teste")

        self.assertTrue(context["produtos"][0]["is_customer_supplied"])

    def test_build_budget_pdf_context_includes_soma_markup(self) -> None:
        workshop = create_workshop(suffix=95)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=95)
        service = create_service(workshop=workshop, suffix=95)

        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            product=product,
            quantity=1,
        )
        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            service=service,
            quantity=1,
        )

        context = build_budget_pdf_context(budget=budget, observacao="Observacao de teste")

        self.assertEqual(context["soma_markup"], Decimal("2.33"))
        self.assertEqual(context["soma_markup_display"], "2,33x")

    def test_build_budget_pdf_context_uses_cost_only_display_for_warranty_budget(self) -> None:
        workshop = create_workshop(suffix=51)
        budget = create_budget(workshop=workshop)
        budget.is_warranty_budget = True
        budget.save(update_fields=["is_warranty_budget"])

        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Produto garantia",
            quantity=2,
            product_cost_price=Money("50.00", "BRL"),
            product_selling_price=Money("100.00", "BRL"),
            shipping=Money("5.00", "BRL"),
        )
        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Servico garantia",
            quantity=1,
            service_cost_price=Money("30.00", "BRL"),
            service_selling_price=Money("90.00", "BRL"),
        )
        budget.discount_value = Money("5.00", "BRL")

        context = build_budget_pdf_context(budget=budget, observacao="Observacao de teste")

        self.assertEqual(context["produtos"][0]["unit_price"], Money("0.00", "BRL"))
        self.assertEqual(context["produtos"][0]["total_price"], Money("105.00", "BRL"))
        self.assertEqual(context["servicos"][0]["unit_price"], Money("0.00", "BRL"))
        self.assertEqual(context["servicos"][0]["total_price"], Money("30.00", "BRL"))
        self.assertEqual(context["desconto"], Money("5.00", "BRL"))
        self.assertEqual(context["total_geral"], Money("130.00", "BRL"))
        self.assertEqual(context["total_profit_product_value"], Money("0.00", "BRL"))
        self.assertEqual(context["total_profit_service_value"], Money("0.00", "BRL"))

    def test_build_budget_pdf_context_zeroes_client_visible_warranty_prices(self) -> None:
        workshop = create_workshop(suffix=15)
        budget = create_budget(workshop=workshop)
        budget.is_warranty_budget = True
        budget.save(update_fields=["is_warranty_budget"])

        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Produto garantia cliente",
            quantity=2,
            product_cost_price=Money("50.00", "BRL"),
            product_selling_price=Money("100.00", "BRL"),
            shipping=Money("5.00", "BRL"),
        )
        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            is_local=True,
            description="Servico garantia cliente",
            quantity=1,
            service_cost_price=Money("30.00", "BRL"),
            service_selling_price=Money("90.00", "BRL"),
        )
        budget.discount_value = Money("5.00", "BRL")

        context = build_budget_pdf_context(budget=budget, observacao="Observacao de teste", zero_warranty_prices=True)

        self.assertEqual(context["produtos"][0]["unit_price"], Money("0.00", "BRL"))
        self.assertEqual(context["produtos"][0]["shipping"], Money("0.00", "BRL"))
        self.assertEqual(context["produtos"][0]["total_price"], Money("0.00", "BRL"))
        self.assertEqual(context["servicos"][0]["unit_price"], Money("0.00", "BRL"))
        self.assertEqual(context["servicos"][0]["total_price"], Money("0.00", "BRL"))
        self.assertEqual(context["desconto"], Money("0.00", "BRL"))
        self.assertEqual(context["total_produtos"], Money("0.00", "BRL"))
        self.assertEqual(context["total_servicos"], Money("0.00", "BRL"))
        self.assertEqual(context["total_geral"], Money("0.00", "BRL"))

    def test_customer_budget_pdf_hides_kit_section(self) -> None:
        workshop = create_workshop(suffix=16)
        budget = create_budget(workshop=workshop)
        direct_product = create_product(workshop=workshop, suffix=161, application="Gol")
        direct_service = create_service(workshop=workshop, suffix=162)
        kit_product = create_product(workshop=workshop, suffix=163, application="Fox")
        kit_service = create_service(workshop=workshop, suffix=164)
        kit = create_kit(workshop=workshop, suffix=165, products=[(kit_product, 1)])
        KitService.objects.create(kit=kit, service=kit_service, quantity=2, duration=kit_service.duration)

        BudgetItem.objects.create(workshop=workshop, budget=budget, product=direct_product, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, service=direct_service, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit, quantity=1)

        context = build_budget_pdf_context(budget=budget, observacao="Observacao de teste", presentation="selected_items")
        html = render_to_string("budget/partials/pdf/visualizarPDF.html", context)

        self.assertEqual(len(context["kits"]), 1)
        self.assertEqual(context["kits"][0]["description"], kit.name)
        self.assertNotIn('<h4 class="font-bold mb-1 uppercase">Kits</h4>', html)
        self.assertNotIn(kit.name, html)

    def test_budget_pdf_template_allows_long_freeform_text_to_wrap(self) -> None:
        workshop = create_workshop(suffix=94)
        customer = create_customer(workshop=workshop, suffix=94)
        vehicle = create_vehicle(workshop=workshop, customer=customer, suffix=94, plate="PDF9494")
        budget = create_budget(workshop=workshop)
        budget.customer = customer
        budget.vehicle = vehicle
        budget.problem_description = "Relato com quebra de linha\n" + ("problema-muito-longo-" * 12)
        budget.save(update_fields=["customer", "vehicle", "problem_description"])

        observation = "Observacao tecnica extensa\n" + ("observacao-sem-espaco-" * 12)
        request = RequestFactory().get("/")
        request.user = User.objects.create_user(username="budget-pdf-user-94", password="123")

        context = build_budget_pdf_context(budget=budget, observacao=observation, request=request)
        html = render_to_string("budget/partials/pdf/visualizarPDF.html", context)

        self.assertIn("overflow-wrap: anywhere;", html)
        self.assertIn("white-space: pre-wrap;", html)
        self.assertNotIn("max-height: 65px;", html)
        self.assertNotIn("max-height: 116px;", html)
        self.assertIn("summary-totals-box", html)
        self.assertIn("preserve-freeform-text", html)

    @patch("apps.budget.pdf_context.get_workshop_logo_file")
    def test_build_budget_pdf_context_uses_logo_saved_in_mongo(self, get_workshop_logo_file_mock) -> None:
        workshop = create_workshop(suffix=97)
        budget = create_budget(workshop=workshop)
        logo_bytes = b"mongo-logo"
        get_workshop_logo_file_mock.return_value = StoredWorkshopFile(
            file_id="mongo-logo-id",
            filename="logo.png",
            content_type="image/png",
            content=logo_bytes,
            uploaded_at=None,
        )

        context = build_budget_pdf_context(budget=budget, observacao="Observacao de teste")

        expected_logo_data_uri = f"data:image/png;base64,{base64.b64encode(logo_bytes).decode('ascii')}"
        self.assertEqual(context["workshop_logo_data_uri"], expected_logo_data_uri)


class BudgetPdfViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=97)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def _create_budget_with_customer_and_vehicle(self, *, suffix: int) -> Budget:
        customer = create_customer(workshop=self.workshop, suffix=suffix)
        vehicle = create_vehicle(workshop=self.workshop, customer=customer, suffix=suffix, plate=f"BGT{suffix:04d}"[:7])
        budget = create_budget(workshop=self.workshop)
        budget.customer = customer
        budget.vehicle = vehicle
        budget.save(update_fields=["customer", "vehicle"])
        return budget

    @staticmethod
    def _build_logo_file(*, content: bytes) -> StoredWorkshopFile:
        return StoredWorkshopFile(
            file_id="mongo-logo-id",
            filename="logo.png",
            content_type="image/png",
            content=content,
            uploaded_at=None,
        )

    @patch("apps.budget.pdf_context.get_workshop_logo_file")
    def test_visualizar_pdf_gestor_renders_workshop_logo(self, get_workshop_logo_file_mock) -> None:
        budget = self._create_budget_with_customer_and_vehicle(suffix=98)
        logo_bytes = b"gestor-logo"
        get_workshop_logo_file_mock.return_value = self._build_logo_file(content=logo_bytes)

        response = self.client.get(reverse("budget:visualizar_pdf_gestor", args=[budget.pk]))

        self.assertEqual(response.status_code, 200)
        expected_logo_data_uri = f"data:image/png;base64,{base64.b64encode(logo_bytes).decode('ascii')}"
        self.assertContains(response, f'src="{expected_logo_data_uri}"', html=False)

    def test_visualizar_pdf_gestor_renders_soma_markup(self) -> None:
        budget = self._create_budget_with_customer_and_vehicle(suffix=105)
        product = create_product(workshop=self.workshop, suffix=105)
        service = create_service(workshop=self.workshop, suffix=105)

        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            product=product,
            quantity=1,
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            service=service,
            quantity=1,
        )

        response = self.client.get(reverse("budget:visualizar_pdf_gestor", args=[budget.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SOMA MARKUP")
        self.assertContains(response, "2,33x")

    @patch("apps.budget.pdf_context.get_workshop_logo_file")
    def test_visualizar_pdf_mecanico_renders_workshop_logo(self, get_workshop_logo_file_mock) -> None:
        budget = self._create_budget_with_customer_and_vehicle(suffix=99)
        logo_bytes = b"mecanico-logo"
        get_workshop_logo_file_mock.return_value = self._build_logo_file(content=logo_bytes)

        response = self.client.get(reverse("budget:visualizar_pdf_mecanico", args=[budget.pk]))

        self.assertEqual(response.status_code, 200)
        expected_logo_data_uri = f"data:image/png;base64,{base64.b64encode(logo_bytes).decode('ascii')}"
        self.assertContains(response, f'src="{expected_logo_data_uri}"', html=False)

    @patch("apps.budget.views.pdf_views.build_workshop_logo_data_uri", return_value="data:image/png;base64,bW9uZ28tbG9nbw==")
    def test_visualizar_pdf_checklist_renders_workshop_logo(self, build_workshop_logo_data_uri_mock) -> None:
        budget = self._create_budget_with_customer_and_vehicle(suffix=100)
        checklist = Checklist.objects.create(workshop=self.workshop, name="Checklist PDF")
        ChecklistItem.objects.create(checklist=checklist, group="Motor", description="Verificar oleo", response_type="SIM_NAO", order=1)

        response = self.client.get(reverse("budget:visualizar_pdf_checklist", args=[budget.pk]), {"checklist": checklist.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'src="data:image/png;base64,bW9uZ28tbG9nbw=="', html=False)
        build_workshop_logo_data_uri_mock.assert_called_once_with(workshop=self.workshop)

    @patch("apps.budget.views.pdf_views.read_checklist_pdf_file")
    def test_visualizar_pdf_checklist_returns_original_imported_pdf(self, read_checklist_pdf_file_mock) -> None:
        budget = self._create_budget_with_customer_and_vehicle(suffix=110)
        checklist = Checklist.objects.create(
            workshop=self.workshop,
            name="Checklist Importado",
            source=Checklist.ChecklistSource.PDF,
            pdf_file_key="workshops/1/pdfs/checklist.pdf",
            pdf_file_name="checklist.pdf",
            pdf_content_type="application/pdf",
        )
        read_checklist_pdf_file_mock.return_value = Mock(content=b"%PDF-1.4 test", filename="checklist.pdf")

        response = self.client.get(reverse("budget:visualizar_pdf_checklist", args=[budget.pk]), {"checklist": checklist.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn('inline; filename="checklist.pdf"', response["Content-Disposition"])
        self.assertEqual(response.content, b"%PDF-1.4 test")
        read_checklist_pdf_file_mock.assert_called_once_with(file_id="workshops/1/pdfs/checklist.pdf")

    def test_pdf_views_render_customer_supplied_product_info(self) -> None:
        budget = self._create_budget_with_customer_and_vehicle(suffix=103)
        supplied_product = create_product(workshop=self.workshop, suffix=103)
        regular_product = create_product(workshop=self.workshop, suffix=104)

        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            product=supplied_product,
            quantity=1,
            is_customer_supplied=True,
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            product=regular_product,
            quantity=1,
            is_customer_supplied=False,
        )

        for url_name in ["budget:visualizar_pdf", "budget:visualizar_pdf_gestor", "budget:visualizar_pdf_mecanico"]:
            response = self.client.get(reverse(url_name, args=[budget.pk]))

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Fornecido pelo cliente?")
            self.assertRegex(response.content.decode(), r">\s*Sim\s*<")
            self.assertRegex(response.content.decode(), r">\s*Não\s*<")

    def test_visualizar_pdf_gestor_product_table_headers_match_rendered_columns(self) -> None:
        budget = self._create_budget_with_customer_and_vehicle(suffix=108)
        product = create_product(workshop=self.workshop, suffix=108)

        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            product=product,
            quantity=1,
        )

        response = self.client.get(reverse("budget:visualizar_pdf_gestor", args=[budget.pk]))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertEqual(content.count("Fornecido pelo cliente?"), 1)
        self.assertEqual(content.count("Valor Unitário"), 1)
        self.assertContains(response, "Frete")
        self.assertContains(response, "Custo")
        self.assertContains(response, "Lucro")
        self.assertNotContains(response, '<th class="p-1 font-semibold text-center whitespace-normal leading-tight">Fornecido pelo cliente</th>', html=False)

    def test_visualizar_pdf_mecanico_product_table_headers_match_rendered_columns(self) -> None:
        budget = self._create_budget_with_customer_and_vehicle(suffix=109)
        product = create_product(workshop=self.workshop, suffix=109)

        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            product=product,
            quantity=1,
        )

        response = self.client.get(reverse("budget:visualizar_pdf_mecanico", args=[budget.pk]))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertEqual(content.count("Fornecido pelo cliente?"), 1)
        self.assertContains(response, "Referência")
        self.assertContains(response, "Localização")
        self.assertContains(response, "Descrição")
        self.assertNotContains(response, '<th class="p-1 font-semibold w-[14%] text-center whitespace-normal leading-tight">Fornecido pelo cliente</th>', html=False)

    def test_pdf_views_display_warranty_label_for_warranty_budget(self) -> None:
        budget = self._create_budget_with_customer_and_vehicle(suffix=106)
        budget.is_warranty_budget = True
        budget.save(update_fields=["is_warranty_budget"])

        for url_name in ["budget:visualizar_pdf", "budget:visualizar_pdf_gestor", "budget:visualizar_pdf_mecanico"]:
            response = self.client.get(reverse(url_name, args=[budget.pk]))

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Orçamento de Garantia")

    def test_visualizar_pdf_zeroes_client_prices_for_warranty_budget(self) -> None:
        budget = self._create_budget_with_customer_and_vehicle(suffix=206)
        budget.is_warranty_budget = True
        budget.save(update_fields=["is_warranty_budget"])

        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            is_local=True,
            description="Produto garantia PDF cliente",
            quantity=2,
            product_cost_price=Money("50.00", "BRL"),
            product_selling_price=Money("100.00", "BRL"),
            shipping=Money("5.00", "BRL"),
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            is_local=True,
            description="Servico garantia PDF cliente",
            quantity=1,
            service_cost_price=Money("30.00", "BRL"),
            service_selling_price=Money("90.00", "BRL"),
        )

        response = self.client.get(reverse("budget:visualizar_pdf", args=[budget.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TOTAL DAS PEÇAS: R$")
        self.assertContains(response, "TOTAL DOS SERVIÇOS: R$")
        self.assertContains(response, "TOTAL GERAL:")
        self.assertNotContains(response, "R$ 105,00")
        self.assertNotContains(response, "R$ 30,00")
        self.assertGreaterEqual(response.content.decode().count("R$\xa00,00"), 5)

    def test_visualizar_pdf_gestor_keeps_internal_warranty_totals(self) -> None:
        budget = self._create_budget_with_customer_and_vehicle(suffix=207)
        budget.is_warranty_budget = True
        budget.save(update_fields=["is_warranty_budget"])

        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            is_local=True,
            description="Produto garantia PDF gestor",
            quantity=2,
            product_cost_price=Money("50.00", "BRL"),
            product_selling_price=Money("100.00", "BRL"),
            shipping=Money("5.00", "BRL"),
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=budget,
            is_local=True,
            description="Servico garantia PDF gestor",
            quantity=1,
            service_cost_price=Money("30.00", "BRL"),
            service_selling_price=Money("90.00", "BRL"),
        )

        response = self.client.get(reverse("budget:visualizar_pdf_gestor", args=[budget.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "R$\xa0105,00", html=False)
        self.assertContains(response, "R$\xa030,00", html=False)

    def test_pdf_views_hide_warranty_label_for_regular_budget(self) -> None:
        budget = self._create_budget_with_customer_and_vehicle(suffix=107)

        for url_name in ["budget:visualizar_pdf", "budget:visualizar_pdf_gestor", "budget:visualizar_pdf_mecanico"]:
            response = self.client.get(reverse(url_name, args=[budget.pk]))

            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "Orçamento de Garantia")

    def test_visualizar_pdf_uses_workshop_observation(self) -> None:
        budget = self._create_budget_with_customer_and_vehicle(suffix=101)
        self.workshop.pdf_observation = "Observacao da oficina"
        self.workshop.save(update_fields=["pdf_observation"])

        response = self.client.get(reverse("budget:visualizar_pdf", args=[budget.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Observacao da oficina")

    def test_save_observation_updates_budget_and_returns_saved_value(self) -> None:
        budget = create_budget(workshop=self.workshop)

        response = self.client.post(
            reverse("budget:save_observation"),
            data=json.dumps({"budget_id": budget.pk, "observation": "Observacao do orcamento"}),
            content_type="application/json",
        )

        budget.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True, "observation": "Observacao do orcamento"})
        self.assertEqual(budget.observations, "Observacao do orcamento")

    def test_save_observation_accepts_more_than_250_chars(self) -> None:
        budget = create_budget(workshop=self.workshop)
        observation = f"observacao longa {'x' * 280}"

        response = self.client.post(
            reverse("budget:save_observation"),
            data=json.dumps({"budget_id": budget.pk, "observation": observation}),
            content_type="application/json",
        )

        budget.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(observation), 250)
        self.assertEqual(budget.observations, sentence_case(observation))
        self.assertEqual(response.json()["observation"], sentence_case(observation))


class BudgetStep6FormTests(TestCase):
    def test_step6_requires_both_datetime_fields(self) -> None:
        workshop = create_workshop(suffix=94)
        budget = create_budget(workshop=workshop)

        request = RequestFactory().post("/")
        request.user = User.objects.create_user(username="budget-step6-user-94", password="123")
        form = BudgetStep6Form(
            data={
                "customer_agreed_departure_at": "",
                "service_expected_completion_at": "",
            },
            instance=budget,
            workshop=workshop,
            request=request,
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["customer_agreed_departure_at"], [Budget.CUSTOMER_AGREED_DEPARTURE_REQUIRED_MESSAGE])
        self.assertEqual(form.errors["service_expected_completion_at"], [Budget.SERVICE_EXPECTED_COMPLETION_REQUIRED_MESSAGE])

    def test_step6_rejects_departure_before_expected_completion(self) -> None:
        workshop = create_workshop(suffix=93)
        budget = create_budget(workshop=workshop)

        request = RequestFactory().post("/")
        request.user = User.objects.create_user(username="budget-step6-user-93", password="123")
        form = BudgetStep6Form(
            data={
                "customer_agreed_departure_at": "2026-05-10T09:00",
                "service_expected_completion_at": "2026-05-10T10:00",
            },
            instance=budget,
            workshop=workshop,
            request=request,
        )

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["customer_agreed_departure_at"], [Budget.STEP6_DATE_ORDER_ERROR_MESSAGE])

    def test_step6_renders_new_datetime_fields(self) -> None:
        workshop = create_workshop(suffix=92)
        budget = create_budget(workshop=workshop)

        request = RequestFactory().get("/")
        request.user = User.objects.create_user(username="budget-step6-user-92", password="123")
        form = BudgetStep6Form(instance=budget, workshop=workshop, request=request)
        html = Template("{% load crispy_forms_tags %}{% crispy form %}").render(Context({"form": form, "csrf_token": "token"}))

        self.assertIn("customer_agreed_departure_at", html)
        self.assertIn("service_expected_completion_at", html)
        self.assertIn("Data de saída combinada com o Cliente", html)
        self.assertIn("Data prevista de término do serviço", html)
        self.assertIn('data-budget-review-date-autosave="1"', html)
        self.assertIn(reverse("budget:autosave_review_date", args=[budget.pk]), html)

    def test_step6_pdf_modal_uses_resend_label_for_sent_signature(self) -> None:
        workshop = create_workshop(suffix=95)
        budget = create_budget(workshop=workshop)
        budget.signature_request_status = SignatureStatus.SENT
        budget.signature_external_id = "env-95"
        budget.save(update_fields=["signature_request_status", "signature_external_id"])

        request = RequestFactory().get("/")
        request.user = User.objects.create_user(username="budget-step6-user-95", password="123")
        form = BudgetStep6Form(instance=budget, workshop=workshop, request=request)
        html = Template("{% load crispy_forms_tags %}{% crispy form %}").render(Context({"form": form, "csrf_token": "token"}))

        self.assertIn("Reenviar Documento", html)
        self.assertIn("data-is-resend", html)
        self.assertIn("Você tem certeza que deseja reenviar este documento para assinatura?", html)
        self.assertIn("Ver não assinado", html)
        self.assertIn("showPdfVariantToggle", html)
        self.assertIn("variant=signed", html)
        self.assertIn("variant=base", html)

    def test_step6_pdf_modal_hides_signed_toggle_when_document_not_sent(self) -> None:
        workshop = create_workshop(suffix=96)
        budget = create_budget(workshop=workshop)

        request = RequestFactory().get("/")
        request.user = User.objects.create_user(username="budget-step6-user-96", password="123")
        form = BudgetStep6Form(instance=budget, workshop=workshop, request=request)
        html = Template("{% load crispy_forms_tags %}{% crispy form %}").render(Context({"form": form, "csrf_token": "token"}))

        self.assertIn("showPdfVariantToggle: false", html)
        self.assertIn('x-show="showPdfVariantToggle"', html)

    def test_step6_pdf_buttons_use_fresh_observation_cache_buster(self) -> None:
        workshop = create_workshop(suffix=68)
        budget = create_budget(workshop=workshop)
        budget.observations = "Observação inicial."
        budget.save(update_fields=["observations"])

        request = RequestFactory().get("/")
        request.user = User.objects.create_user(username="budget-step6-user-68", password="123")
        form = BudgetStep6Form(instance=budget, workshop=workshop, request=request)
        html = Template("{% load crispy_forms_tags %}{% crispy form %}").render(Context({"form": form, "csrf_token": "token"}))

        self.assertIn("window.budgetPdfCacheVersion = Date.now().toString();", html)
        self.assertIn("function openBudgetPdfModal(detail)", html)
        self.assertIn("function withBudgetPdfCache(url)", html)
        self.assertIn("async function saveObservation", html)
        self.assertIn("payload.observation", html)
        self.assertIn("openBudgetPdfModal({", html)
        self.assertIn("_pdfv=", html)

    def test_step6_keeps_approval_and_signature_available_when_stock_is_insufficient(self) -> None:
        workshop = create_workshop(suffix=97)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=97)
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=3)

        stock_product = StockProduct.objects.get(workshop=workshop, product=product)
        stock_product.current_quantity = 1
        stock_product.save(update_fields=["current_quantity"])

        request = RequestFactory().get("/")
        request.user = User.objects.create_user(username="budget-step6-user-97", password="123")
        form = BudgetStep6Form(instance=budget, workshop=workshop, request=request)
        html = Template("{% load crispy_forms_tags %}{% crispy form %}").render(Context({"form": form, "csrf_token": "token"}))

        self.assertNotIn("Existem pecas com quantidade acima do estoque disponivel", html)
        self.assertIn("signatureBlocked: false", html)
        self.assertIn(f"onclick=\"updateBudgetStatus({budget.pk}, 'approve')\"", html)

    def test_step6_blocks_only_approval_when_review_dates_are_missing(self) -> None:
        workshop = create_workshop(suffix=70)
        budget = create_budget(workshop=workshop)
        budget.customer_agreed_departure_at = timezone.now()
        budget.service_expected_completion_at = budget.customer_agreed_departure_at + timedelta(days=1)
        budget.save(update_fields=["customer_agreed_departure_at", "service_expected_completion_at"])

        request = RequestFactory().get("/")
        request.user = User.objects.create_user(username="budget-step6-user-70", password="123")
        form = BudgetStep6Form(instance=budget, workshop=workshop, request=request)
        html = Template("{% load crispy_forms_tags %}{% crispy form %}").render(Context({"form": form, "csrf_token": "token"}))

        self.assertIn(Budget.STEP6_DATE_ORDER_ERROR_MESSAGE, html)
        self.assertIn("showBlockedStep6Action", html)
        self.assertIn(f"onclick=\"updateBudgetStatus({budget.pk}, 'cancel')\"", html)
        self.assertIn(f"onclick=\"updateBudgetStatus({budget.pk}, 'reject')\"", html)
        self.assertIn("signatureBlocked: false", html)

    def test_step6_service_table_keeps_kit_services_out_of_direct_service_rows(self) -> None:
        workshop = create_workshop(suffix=66)
        budget = create_budget(workshop=workshop)
        direct_service = create_service(workshop=workshop, suffix=661)
        kit_service = create_service(workshop=workshop, suffix=662)
        kit = create_kit(workshop=workshop, suffix=663, products=[])
        KitService.objects.create(kit=kit, service=kit_service, quantity=2, duration=kit_service.duration)

        BudgetItem.objects.create(workshop=workshop, budget=budget, service=direct_service, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit, quantity=1)

        rows = _render_budget_items_rows(budget, step6=True)

        self.assertIn(direct_service.name, rows["service"])
        self.assertNotIn(kit_service.name, rows["service"])
        self.assertIn(kit.name, rows["kit"])

    def test_step6_uses_workshop_observation(self) -> None:
        workshop = create_workshop(suffix=69)
        workshop.pdf_observation = "Observacao da oficina"
        workshop.save(update_fields=["pdf_observation"])

        budget = create_budget(workshop=workshop)

        request = RequestFactory().get("/")
        request.user = User.objects.create_user(username="budget-step6-user-69", password="123")
        form = BudgetStep6Form(instance=budget, workshop=workshop, request=request)
        html = Template("{% load crispy_forms_tags %}{% crispy form %}").render(Context({"form": form, "csrf_token": "token"}))

        self.assertIn("Observacao da oficina", html)

    def test_step6_observation_field_has_no_character_limit(self) -> None:
        workshop = create_workshop(suffix=71)
        budget = create_budget(workshop=workshop)

        request = RequestFactory().get("/")
        request.user = User.objects.create_user(username="budget-step6-user-71", password="123")
        form = BudgetStep6Form(instance=budget, workshop=workshop, request=request)
        html = Template("{% load crispy_forms_tags %}{% crispy form %}").render(Context({"form": form, "csrf_token": "token"}))

        self.assertNotIn('maxlength="250"', html)
        self.assertNotIn("/ 250", html)


class BudgetStep6WorkflowTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=90)
        self.budget = create_budget(workshop=self.workshop)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_update_step6_saves_review_and_stays_on_same_step(self) -> None:
        response = self.client.post(
            f"{reverse('budget:budget_update', kwargs={'pk': self.budget.pk})}?step=6",
            {
                "customer_agreed_departure_at": "2026-05-12T18:00",
                "service_expected_completion_at": "2026-05-12T17:00",
            },
        )

        self.budget.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), f"{reverse('budget:budget_update', kwargs={'pk': self.budget.pk})}?step=6")
        self.assertIsNotNone(self.budget.customer_agreed_departure_at)
        self.assertIsNotNone(self.budget.service_expected_completion_at)

    def test_autosave_review_date_saves_single_field(self) -> None:
        self.budget.customer_agreed_departure_at = None
        self.budget.service_expected_completion_at = None
        self.budget.save(update_fields=["customer_agreed_departure_at", "service_expected_completion_at"])

        response = self.client.post(
            reverse("budget:autosave_review_date", args=[self.budget.pk]),
            {
                "field": "service_expected_completion_at",
                "value": "2026-05-12T17:00",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.budget.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"ok": True})
        self.assertIsNone(self.budget.customer_agreed_departure_at)
        self.assertIsNotNone(self.budget.service_expected_completion_at)

    def test_autosave_review_date_rejects_departure_before_expected_completion(self) -> None:
        self.budget.customer_agreed_departure_at = None
        self.budget.service_expected_completion_at = datetime(2026, 5, 12, 17, 0, tzinfo=timezone.get_current_timezone())
        self.budget.save(update_fields=["customer_agreed_departure_at", "service_expected_completion_at"])

        response = self.client.post(
            reverse("budget:autosave_review_date", args=[self.budget.pk]),
            {
                "field": "customer_agreed_departure_at",
                "value": "2026-05-12T16:00",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.budget.refresh_from_db()

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"ok": False, "error": Budget.STEP6_DATE_ORDER_ERROR_MESSAGE})
        self.assertIsNone(self.budget.customer_agreed_departure_at)

    def test_update_budget_status_allows_cancel_when_step6_dates_are_missing(self) -> None:
        self.budget.customer_agreed_departure_at = None
        self.budget.service_expected_completion_at = None
        self.budget.save(update_fields=["customer_agreed_departure_at", "service_expected_completion_at"])

        response = self.client.post(reverse("budget:update_budget_status", args=[self.budget.pk, "cancel"]))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"success": True})
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.status, BudgetStatus.CANCELLED)

    def test_update_budget_status_blocks_cancel_when_active_workorder_exists(self) -> None:
        WorkOrder.objects.create(workshop=self.workshop, budget=self.budget, status=WorkOrderStatus.DRAFT)
        WorkOrder.objects.create(workshop=self.workshop, budget=self.budget, status=WorkOrderStatus.DRAFT)

        response = self.client.post(reverse("budget:update_budget_status", args=[self.budget.pk, "cancel"]))

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(
            response.content,
            {
                "success": False,
                "error": "Já foi gerada uma ordem de serviço para este orçamento. Cancele a ordem de serviço primeiro para depois cancelar o orçamento.",
            },
        )
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.status, BudgetStatus.APPROVED)

    def test_update_budget_status_allows_cancel_when_only_cancelled_workorder_exists(self) -> None:
        self.budget.status = BudgetStatus.APPROVED
        self.budget.save(update_fields=["status"])
        self.budget.workorders.update(status=WorkOrderStatus.CANCELLED)

        response = self.client.post(reverse("budget:update_budget_status", args=[self.budget.pk, "cancel"]))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"success": True})
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.status, BudgetStatus.CANCELLED)

    def test_update_budget_status_allows_reject_when_step6_dates_are_missing(self) -> None:
        self.budget.customer_agreed_departure_at = None
        self.budget.service_expected_completion_at = None
        self.budget.save(update_fields=["customer_agreed_departure_at", "service_expected_completion_at"])

        response = self.client.post(reverse("budget:update_budget_status", args=[self.budget.pk, "reject"]))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"success": True})
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.status, BudgetStatus.REJECTED)

    def test_update_budget_status_blocks_approve_when_step6_dates_are_missing(self) -> None:
        self.budget.customer_agreed_departure_at = None
        self.budget.service_expected_completion_at = None
        self.budget.save(update_fields=["customer_agreed_departure_at", "service_expected_completion_at"])

        response = self.client.post(reverse("budget:update_budget_status", args=[self.budget.pk, "approve"]))

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(
            response.content,
            {
                "success": False,
                "error": f"Nao e possivel aprovar. {Budget.CUSTOMER_AGREED_DEPARTURE_REQUIRED_MESSAGE} {Budget.SERVICE_EXPECTED_COMPLETION_REQUIRED_MESSAGE}",
            },
        )

    def test_update_budget_status_reopen_requires_reason(self) -> None:
        self.budget.status = BudgetStatus.CANCELLED
        self.budget.save(update_fields=["status"])

        response = self.client.post(reverse("budget:update_budget_status", args=[self.budget.pk, "reopen"]), data={"reopen_reason": ""})

        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"success": False, "error": "A justificativa da reabertura é obrigatória."})
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.status, BudgetStatus.CANCELLED)

    def test_update_budget_status_reopen_creates_history_entry(self) -> None:
        self.budget.status = BudgetStatus.CANCELLED
        self.budget.save(update_fields=["status"])

        response = self.client.post(
            reverse("budget:update_budget_status", args=[self.budget.pk, "reopen"]),
            data={"reopen_reason": "Cliente solicitou nova revisão."},
        )

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"success": True})
        self.budget.refresh_from_db()
        self.assertEqual(self.budget.status, BudgetStatus.WAITING_REVIEW)

        history_entry = BudgetHistory.objects.get(budget=self.budget, action=BudgetHistory.Action.REOPENED)
        self.assertEqual(history_entry.reason, "Cliente solicitou nova revisão.")
        self.assertEqual(history_entry.user_id, self.user.pk)


class BudgetLinkWorkflowTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=19)
        self.current_budget = create_budget(workshop=self.workshop)
        self.reference_budget = create_budget(workshop=self.workshop)
        self.other_reference_budget = create_budget(workshop=self.workshop)

        self.customer = create_customer(workshop=self.workshop, suffix=191)
        self.current_vehicle = create_vehicle(workshop=self.workshop, customer=self.customer, suffix=191, plate="BDG1911")
        self.other_vehicle = create_vehicle(workshop=self.workshop, customer=self.customer, suffix=192, plate="BDG1922")

        self.current_budget.customer = self.customer
        self.current_budget.vehicle = self.current_vehicle
        self.current_budget.save(update_fields=["customer", "vehicle"])

        self.reference_budget.customer = self.customer
        self.reference_budget.vehicle = self.current_vehicle
        self.reference_budget.save(update_fields=["customer", "vehicle"])

        self.other_reference_budget.customer = self.customer
        self.other_reference_budget.vehicle = self.other_vehicle
        self.other_reference_budget.save(update_fields=["customer", "vehicle"])

        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_link_budget_success(self) -> None:
        response = self.client.post(
            reverse("budget:budget_link_process", args=[self.current_budget.pk]),
            data={"reference_budget_id": str(self.reference_budget.pk)},
            HTTP_HX_REQUEST="true",
        )

        self.current_budget.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.current_budget.reference_budget_id, self.reference_budget.pk)

    def test_unlink_budget_success(self) -> None:
        self.current_budget.reference_budget = self.reference_budget
        self.current_budget.save(update_fields=["reference_budget"])

        response = self.client.post(
            reverse("budget:budget_unlink_process", args=[self.current_budget.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.current_budget.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.current_budget.reference_budget_id)

    def test_link_budget_to_itself_fails(self) -> None:
        response = self.client.post(
            reverse("budget:budget_link_process", args=[self.current_budget.pk]),
            data={"reference_budget_id": str(self.current_budget.pk)},
            HTTP_HX_REQUEST="true",
        )

        self.current_budget.refresh_from_db()
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"success": False, "error": "Não é possível vincular um orçamento a ele mesmo."})
        self.assertIsNone(self.current_budget.reference_budget_id)

    def test_link_budget_when_already_linked_fails(self) -> None:
        self.current_budget.reference_budget = self.reference_budget
        self.current_budget.save(update_fields=["reference_budget"])

        response = self.client.post(
            reverse("budget:budget_link_process", args=[self.current_budget.pk]),
            data={"reference_budget_id": str(self.other_reference_budget.pk)},
            HTTP_HX_REQUEST="true",
        )

        self.current_budget.refresh_from_db()
        self.assertEqual(response.status_code, 409)
        self.assertJSONEqual(
            response.content,
            {
                "success": False,
                "error": "Este orçamento já está vinculado. Desvincule antes de realizar um novo vínculo.",
            },
        )
        self.assertEqual(self.current_budget.reference_budget_id, self.reference_budget.pk)

    def test_link_search_lists_only_budgets_from_same_vehicle(self) -> None:
        response = self.client.get(
            reverse("budget:budget_link_search", args=[self.current_budget.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.current_vehicle.plate)
        self.assertNotContains(response, self.other_vehicle.plate)

    def test_link_budget_fails_when_reference_budget_has_different_vehicle(self) -> None:
        response = self.client.post(
            reverse("budget:budget_link_process", args=[self.current_budget.pk]),
            data={"reference_budget_id": str(self.other_reference_budget.pk)},
            HTTP_HX_REQUEST="true",
        )

        self.current_budget.refresh_from_db()
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"success": False, "error": "Só é possível vincular orçamentos do mesmo veículo."})
        self.assertIsNone(self.current_budget.reference_budget_id)


class BudgetProductIssueTests(TestCase):
    def test_step4_product_rows_render_stock_and_invalid_ncm_warnings(self) -> None:
        workshop = create_workshop(suffix=98)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=98)
        product.ncm = ""
        product.save(update_fields=["ncm"])
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=3)

        stock_product = StockProduct.objects.get(workshop=workshop, product=product)
        stock_product.current_quantity = 1
        stock_product.save(update_fields=["current_quantity"])

        rows = _render_budget_items_rows(budget, step6=False)

        self.assertIn("Excede o estoque em 2 pecas.", rows["product"])
        self.assertIn("Produto com NCM invalido.", rows["product"])

    def test_approve_budget_allows_stock_issue(self) -> None:
        workshop = create_workshop(suffix=99)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=99)
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=2)

        stock_product = StockProduct.objects.get(workshop=workshop, product=product)
        stock_product.current_quantity = 1
        stock_product.save(update_fields=["current_quantity"])

        approve_budget_with_stock(budget=budget)

        budget.refresh_from_db()
        self.assertEqual(budget.status, BudgetStatus.APPROVED)

    @patch("apps.budget.views.workflow_views.send_budget_for_signature")
    def test_trigger_signature_send_if_needed_allows_stock_issue(self, send_signature_mock) -> None:
        workshop = create_workshop(suffix=67)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=67)
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=2)

        stock_product = StockProduct.objects.get(workshop=workshop, product=product)
        stock_product.current_quantity = 1
        stock_product.save(update_fields=["current_quantity"])

        send_signature_mock.return_value = SignatureDeliveryResult(
            envelope_id="env-67",
            document_id="doc-67",
            provider="supersign",
            raw_response={"ok": True},
        )

        toast_type, toast_message, redirect_url = trigger_signature_send_if_needed(request=RequestFactory().post("/"), budget=budget)

        budget.refresh_from_db()
        self.assertEqual(toast_type, "success")
        self.assertEqual(toast_message, "Orçamento enviado para assinatura do cliente.")
        self.assertEqual(redirect_url, reverse("budget:budget_list"))
        self.assertEqual(budget.signature_request_status, SignatureStatus.SENT)

    @patch("apps.budget.views.workflow_views.send_budget_for_signature")
    def test_trigger_signature_send_if_needed_allows_invalid_ncm(self, send_signature_mock) -> None:
        workshop = create_workshop(suffix=68)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=68)
        product.ncm = ""
        product.save(update_fields=["ncm"])
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=1)

        stock_product = StockProduct.objects.get(workshop=workshop, product=product)
        stock_product.current_quantity = 5
        stock_product.save(update_fields=["current_quantity"])

        send_signature_mock.return_value = SignatureDeliveryResult(
            envelope_id="env-68",
            document_id="doc-68",
            provider="supersign",
            raw_response={"ok": True},
        )

        toast_type, toast_message, redirect_url = trigger_signature_send_if_needed(request=RequestFactory().post("/"), budget=budget)

        budget.refresh_from_db()
        self.assertEqual(toast_type, "success")
        self.assertEqual(toast_message, "Orçamento enviado para assinatura do cliente.")
        self.assertEqual(redirect_url, reverse("budget:budget_list"))
        self.assertEqual(budget.signature_request_status, SignatureStatus.SENT)

    @patch("apps.budget.views.workflow_views.send_budget_for_signature")
    def test_trigger_signature_send_if_needed_allows_missing_step6_dates(self, send_signature_mock) -> None:
        workshop = create_workshop(suffix=71)
        budget = create_budget(workshop=workshop)
        budget.customer_agreed_departure_at = None
        budget.service_expected_completion_at = None
        budget.save(update_fields=["customer_agreed_departure_at", "service_expected_completion_at"])

        send_signature_mock.return_value = SignatureDeliveryResult(
            envelope_id="env-71",
            document_id="doc-71",
            provider="supersign",
            raw_response={"ok": True},
        )

        toast_type, toast_message, redirect_url = trigger_signature_send_if_needed(request=RequestFactory().post("/"), budget=budget)

        budget.refresh_from_db()
        self.assertEqual(toast_type, "success")
        self.assertEqual(toast_message, "Orçamento enviado para assinatura do cliente.")
        self.assertEqual(redirect_url, reverse("budget:budget_list"))
        self.assertEqual(budget.signature_request_status, SignatureStatus.SENT)


class BudgetQuickCreateProductValidationTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=99)
        self.budget = create_budget(workshop=self.workshop)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_quick_create_product_shows_duplicate_name_error(self) -> None:
        existing_product = create_product(workshop=self.workshop, suffix=99)

        response = self.client.post(
            reverse("budget:quick_create_item", args=[self.budget.pk, "product"]),
            {
                "code": "P-999",
                "unit": Product.Unit.UND,
                "name": existing_product.name,
                "group": existing_product.group.pk,
                "cost_price_0": "10.00",
                "cost_price_1": "BRL",
                "selling_price_0": "20.00",
                "selling_price_1": "BRL",
                "modal_context": "parent",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Já existe um produto com este nome.")
        self.assertEqual(Product.objects.filter(workshop=self.workshop, name=existing_product.name).count(), 1)
        self.assertFalse(BudgetItem.objects.filter(budget=self.budget, product__name=existing_product.name).exists())

    def test_register_local_product_shows_duplicate_name_error(self) -> None:
        existing_product = create_product(workshop=self.workshop, suffix=100)
        local_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            description="Produto local 100",
            quantity=1,
            product_cost_price=Money("10.00", "BRL"),
            product_selling_price=Money("20.00", "BRL"),
            shipping=Money("0.00", "BRL"),
            is_local=True,
        )

        response = self.client.post(
            reverse("budget:register_local_item", args=[self.budget.pk, local_item.pk]),
            {
                "code": "P-1000",
                "unit": Product.Unit.UND,
                "name": existing_product.name,
                "group": existing_product.group.pk,
                "cost_price_0": "10.00",
                "cost_price_1": "BRL",
                "selling_price_0": "20.00",
                "selling_price_1": "BRL",
            },
            HTTP_HX_REQUEST="true",
        )

        local_item.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Retarget"], "#modal-container")
        self.assertContains(response, "Já existe um produto com este nome.")
        self.assertEqual(Product.objects.filter(workshop=self.workshop, name=existing_product.name).count(), 1)
        self.assertTrue(local_item.is_local)
        self.assertIsNone(local_item.product)

    def test_quick_create_product_modal_shows_similar_name_lookup(self) -> None:
        response = self.client.get(
            reverse("budget:quick_create_item", args=[self.budget.pk, "product"]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'hx-get="/catalog/products/search/"')
        self.assertContains(response, 'hx-vals="{&quot;quick_name_lookup&quot;: &quot;1&quot;}"')
        self.assertContains(response, 'id="product-name-suggestions"')

    def test_quick_create_product_accepts_optional_ncm(self) -> None:
        group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo NCM Rapido")

        response = self.client.post(
            reverse("budget:quick_create_item", args=[self.budget.pk, "product"]),
            {
                "code": "P-NCM-99",
                "unit": Product.Unit.UND,
                "name": "Produto com NCM Rapido",
                "group": group.pk,
                "cost_price_0": "10.00",
                "cost_price_1": "BRL",
                "selling_price_0": "20.00",
                "selling_price_1": "BRL",
                "ncm": "87089990",
                "modal_context": "parent",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        product = Product.objects.get(workshop=self.workshop, code="P-NCM-99")
        self.assertEqual(product.ncm, "87089990")

    def test_register_local_product_accepts_optional_ncm(self) -> None:
        group = CatalogGroup.objects.create(workshop=self.workshop, name="Grupo Registro NCM")
        local_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            description="Produto local NCM",
            quantity=1,
            product_cost_price=Money("10.00", "BRL"),
            product_selling_price=Money("20.00", "BRL"),
            shipping=Money("0.00", "BRL"),
            is_local=True,
        )

        response = self.client.post(
            reverse("budget:register_local_item", args=[self.budget.pk, local_item.pk]),
            {
                "code": "P-REG-NCM-99",
                "unit": Product.Unit.UND,
                "name": "Produto Registro NCM",
                "group": group.pk,
                "cost_price_0": "10.00",
                "cost_price_1": "BRL",
                "selling_price_0": "20.00",
                "selling_price_1": "BRL",
                "ncm": "87089990",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        local_item.refresh_from_db()
        self.assertFalse(local_item.is_local)
        assert local_item.product is not None
        self.assertEqual(local_item.product.ncm, "87089990")

    def test_budget_item_updates_product_last_used_price(self) -> None:
        product = create_product(workshop=self.workshop, suffix=1010)
        product.last_used_price = None
        product.save(update_fields=["last_used_price"])

        budget_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=product,
            quantity=1,
        )

        product.refresh_from_db()
        self.assertEqual(budget_item.product_selling_price, Money("15.00", "BRL"))
        self.assertEqual(product.last_used_price, Money("15.00", "BRL"))

    def test_update_master_requires_confirmation_for_price_below_last_used_price(self) -> None:
        product = create_product(workshop=self.workshop, suffix=1011)
        product.last_used_price = Money("30.00", "BRL")
        product.selling_price = Money("40.00", "BRL")
        product.save(update_fields=["last_used_price", "selling_price"])
        budget_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=product,
            quantity=1,
        )

        response = self.client.post(
            reverse("budget:edit_item", args=[self.budget.pk, budget_item.pk]),
            {
                "description": budget_item.description,
                "quantity": "1",
                "product_cost_price_0": "10.00",
                "product_cost_price_1": "BRL",
                "product_selling_price_0": "20.00",
                "product_selling_price_1": "BRL",
                "shipping_0": "0.00",
                "shipping_1": "BRL",
                "ncm": product.ncm,
                "action": "update_master",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Último valor usado: R$ 40,00")
        budget_item.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(budget_item.product_selling_price, Money("40.00", "BRL"))
        self.assertEqual(product.selling_price, Money("40.00", "BRL"))

    def test_update_master_allows_confirmed_price_below_last_used_price(self) -> None:
        product = create_product(workshop=self.workshop, suffix=1012)
        product.last_used_price = Money("30.00", "BRL")
        product.selling_price = Money("40.00", "BRL")
        product.save(update_fields=["last_used_price", "selling_price"])
        budget_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=product,
            quantity=1,
        )

        response = self.client.post(
            reverse("budget:edit_item", args=[self.budget.pk, budget_item.pk]),
            {
                "description": budget_item.description,
                "quantity": "1",
                "product_cost_price_0": "10.00",
                "product_cost_price_1": "BRL",
                "product_selling_price_0": "20.00",
                "product_selling_price_1": "BRL",
                "shipping_0": "0.00",
                "shipping_1": "BRL",
                "ncm": product.ncm,
                "action": "update_master",
                "confirm_lower_price": "1",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Redirect", response)
        budget_item.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(budget_item.product_selling_price, Money("20.00", "BRL"))
        self.assertEqual(product.selling_price, Money("20.00", "BRL"))
        self.assertEqual(product.last_used_price, Money("20.00", "BRL"))

    def test_save_only_requires_confirmation_for_price_below_last_used_price(self) -> None:
        product = create_product(workshop=self.workshop, suffix=1013)
        product.last_used_price = Money("30.00", "BRL")
        product.selling_price = Money("40.00", "BRL")
        product.save(update_fields=["last_used_price", "selling_price"])
        budget_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=product,
            quantity=1,
        )

        response = self.client.post(
            reverse("budget:edit_item", args=[self.budget.pk, budget_item.pk]),
            {
                "description": budget_item.description,
                "quantity": "1",
                "product_cost_price_0": "10.00",
                "product_cost_price_1": "BRL",
                "product_selling_price_0": "20.00",
                "product_selling_price_1": "BRL",
                "shipping_0": "0.00",
                "shipping_1": "BRL",
                "ncm": product.ncm,
                "action": "save_only",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Último valor usado: R$ 40,00")
        budget_item.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(budget_item.product_selling_price, Money("40.00", "BRL"))
        self.assertEqual(product.selling_price, Money("40.00", "BRL"))
        self.assertEqual(product.last_used_price, Money("40.00", "BRL"))

    def test_queue_save_only_requires_confirmation_for_price_below_last_used_price_and_preserves_queue_mode(self) -> None:
        product = create_product(workshop=self.workshop, suffix=10131)
        product.last_used_price = Money("30.00", "BRL")
        product.selling_price = Money("40.00", "BRL")
        product.save(update_fields=["last_used_price", "selling_price"])
        budget_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=product,
            quantity=1,
        )

        response = self.client.post(
            reverse("budget:edit_item", args=[self.budget.pk, budget_item.pk]),
            {
                "description": budget_item.description,
                "quantity": "1",
                "product_cost_price_0": "10.00",
                "product_cost_price_1": "BRL",
                "product_selling_price_0": "20.00",
                "product_selling_price_1": "BRL",
                "shipping_0": "0.00",
                "shipping_1": "BRL",
                "ncm": product.ncm,
                "action": "save_only",
                "in_queue": "true",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Último valor usado: R$ 40,00")
        self.assertContains(response, 'name="in_queue" value="true"')
        self.assertNotContains(response, 'class="btn btn-primary gap-2 js-save-local"')
        budget_item.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(budget_item.product_selling_price, Money("40.00", "BRL"))
        self.assertEqual(product.last_used_price, Money("40.00", "BRL"))

    def test_save_only_allows_confirmed_price_below_last_used_price(self) -> None:
        product = create_product(workshop=self.workshop, suffix=1014)
        product.last_used_price = Money("30.00", "BRL")
        product.selling_price = Money("40.00", "BRL")
        product.save(update_fields=["last_used_price", "selling_price"])
        budget_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=product,
            quantity=1,
        )

        response = self.client.post(
            reverse("budget:edit_item", args=[self.budget.pk, budget_item.pk]),
            {
                "description": budget_item.description,
                "quantity": "1",
                "product_cost_price_0": "10.00",
                "product_cost_price_1": "BRL",
                "product_selling_price_0": "20.00",
                "product_selling_price_1": "BRL",
                "shipping_0": "0.00",
                "shipping_1": "BRL",
                "ncm": product.ncm,
                "action": "save_only",
                "confirm_lower_price": "1",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Redirect", response)
        budget_item.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(budget_item.product_selling_price, Money("20.00", "BRL"))
        self.assertEqual(product.selling_price, Money("40.00", "BRL"))
        self.assertEqual(product.last_used_price, Money("20.00", "BRL"))

    def test_queue_save_only_allows_confirmed_price_below_last_used_price(self) -> None:
        product = create_product(workshop=self.workshop, suffix=10141)
        product.last_used_price = Money("30.00", "BRL")
        product.selling_price = Money("40.00", "BRL")
        product.save(update_fields=["last_used_price", "selling_price"])
        budget_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=product,
            quantity=1,
        )

        response = self.client.post(
            reverse("budget:edit_item", args=[self.budget.pk, budget_item.pk]),
            {
                "description": budget_item.description,
                "quantity": "1",
                "product_cost_price_0": "10.00",
                "product_cost_price_1": "BRL",
                "product_selling_price_0": "20.00",
                "product_selling_price_1": "BRL",
                "shipping_0": "0.00",
                "shipping_1": "BRL",
                "ncm": product.ncm,
                "action": "save_only",
                "confirm_lower_price": "1",
                "in_queue": "true",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Redirect", response)
        budget_item.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(budget_item.product_selling_price, Money("20.00", "BRL"))
        self.assertEqual(product.selling_price, Money("40.00", "BRL"))
        self.assertEqual(product.last_used_price, Money("20.00", "BRL"))

    def test_queue_quick_edit_product_modal_renders_queue_save_trigger_and_full_title(self) -> None:
        product = create_product(workshop=self.workshop, suffix=10142)
        product.name = "Produto com nome muito grande para aparecer inteiro na fila"
        product.save(update_fields=["name"])
        budget_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=product,
            quantity=1,
        )

        response = self.client.get(
            reverse("budget:edit_item", args=[self.budget.pk, budget_item.pk]),
            {"in_queue": "true"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="hidden js-save-local js-queue-save-trigger"')
        self.assertContains(response, 'class="font-bold text-xl text-base-content flex-1 min-w-0 truncate"')
        self.assertContains(response, "Produto com nome muito grande para aparecer inteiro na fila")

    def test_quick_edit_product_modal_shows_ncm_field(self) -> None:
        product = create_product(workshop=self.workshop, suffix=102)
        budget_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=product,
            quantity=1,
        )

        response = self.client.get(
            reverse("budget:edit_item", args=[self.budget.pk, budget_item.pk]),
            HTTP_HX_REQUEST="true",
        )
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="ncm"')
        self.assertContains(response, 'value="87089990"')
        self.assertContains(response, 'name="is_customer_supplied"')
        self.assertContains(response, 'id="stock-quantity-reference"')
        self.assertNotContains(response, 'type="number"')
        self.assertLess(content.index('id="stock-quantity-reference"'), content.index('name="is_customer_supplied"'))

    def test_quick_edit_product_updates_ncm(self) -> None:
        product = create_product(workshop=self.workshop, suffix=103)
        budget_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=product,
            quantity=1,
        )

        response = self.client.post(
            reverse("budget:edit_item", args=[self.budget.pk, budget_item.pk]),
            {
                "description": budget_item.description,
                "quantity": "1",
                "product_cost_price_0": "10.00",
                "product_cost_price_1": "BRL",
                "product_selling_price_0": "15.00",
                "product_selling_price_1": "BRL",
                "shipping_0": "0.00",
                "shipping_1": "BRL",
                "is_customer_supplied": "on",
                "ncm": "12345678",
                "action": "save_only",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Redirect", response)
        budget_item.refresh_from_db()
        product.refresh_from_db()
        self.assertTrue(budget_item.is_customer_supplied)
        self.assertEqual(product.ncm, "12345678")

    def test_quick_edit_service_modal_hides_customer_supplied_field(self) -> None:
        service = create_service(workshop=self.workshop, suffix=104)
        budget_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            service=service,
            quantity=1,
        )

        response = self.client.get(
            reverse("budget:edit_item", args=[self.budget.pk, budget_item.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="is_customer_supplied"')

    def test_product_row_shows_customer_supplied_badge(self) -> None:
        product = create_product(workshop=self.workshop, suffix=105)
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=product,
            quantity=1,
            is_customer_supplied=True,
        )

        rows = _render_budget_items_rows(self.budget, step6=False)

        self.assertIn("badge-success", rows["product"])
        self.assertIn(">Sim<", rows["product"])
        self.assertIn('<td class="text-center">', rows["product"])

    def test_product_row_shows_customer_supplied_badge_on_step6(self) -> None:
        product = create_product(workshop=self.workshop, suffix=106)
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=product,
            quantity=1,
            is_customer_supplied=True,
        )

        rows = _render_budget_items_rows(self.budget, step6=True)

        self.assertIn("badge-success", rows["product"])
        self.assertIn(">Sim<", rows["product"])
        self.assertIn('<td class="text-center">', rows["product"])

    def test_warranty_budget_rows_show_zero_sale_and_cost_based_totals(self) -> None:
        self.budget.is_warranty_budget = True
        self.budget.save(update_fields=["is_warranty_budget"])

        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            is_local=True,
            description="Produto garantia",
            quantity=2,
            product_cost_price=Money("10.00", "BRL"),
            product_selling_price=Money("40.00", "BRL"),
            shipping=Money("5.00", "BRL"),
        )
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            is_local=True,
            description="Servico garantia",
            quantity=1,
            service_cost_price=Money("30.00", "BRL"),
            service_selling_price=Money("80.00", "BRL"),
        )

        rows = _render_budget_items_rows(self.budget, step6=False)

        self.assertIn("R$\xa00,00", rows["product"])
        self.assertIn("R$\xa025,00", rows["product"])
        self.assertIn("R$\xa00,00", rows["service"])
        self.assertIn("R$\xa030,00", rows["service"])

    def test_product_row_shows_not_customer_supplied_badge_by_default(self) -> None:
        product = create_product(workshop=self.workshop, suffix=107)
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=product,
            quantity=1,
        )

        rows = _render_budget_items_rows(self.budget, step6=False)

        self.assertIn("badge-ghost", rows["product"])
        self.assertIn(">Não<", rows["product"])

    def test_step4_and_step6_product_tables_show_customer_column_header(self) -> None:
        request = RequestFactory().get("/")
        request.user = self.user
        step4_form = BudgetStep4Form(instance=self.budget, workshop=self.workshop, request=request)
        step4_html = Template("{% load crispy_forms_tags %}{% crispy form %}").render(Context({"form": step4_form, "csrf_token": "token"}))

        step6_form = BudgetStep6Form(instance=self.budget, workshop=self.workshop, request=request)
        step6_html = Template("{% load crispy_forms_tags %}{% crispy form %}").render(Context({"form": step6_form, "csrf_token": "token"}))

        self.assertIn("Trago pelo cliente?", step4_html)
        self.assertIn("Trago pelo cliente?", step6_html)

    def test_product_name_lookup_returns_similar_products(self) -> None:
        create_product(workshop=self.workshop, suffix=101)

        response = self.client.get(
            reverse("catalog:product_search"),
            {
                "quick_name_lookup": "1",
                "name": "Produto 101",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Encontramos produtos com nome parecido")
        self.assertContains(response, "Produto 101")


class ServiceNameSuggestionTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=12)
        self.budget = create_budget(workshop=self.workshop)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_service_create_page_shows_similar_name_lookup(self) -> None:
        response = self.client.get(reverse("catalog:services_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'hx-get="/catalog/services/search/"')
        self.assertContains(response, 'id="name-suggestions"')

    def test_quick_create_service_modal_shows_similar_name_lookup(self) -> None:
        response = self.client.get(
            reverse("budget:quick_create_item", args=[self.budget.pk, "service"]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'hx-get="/catalog/services/search/"')
        self.assertContains(response, 'hx-vals="{&quot;target_id&quot;: &quot;service-name-suggestions&quot;}"')
        self.assertContains(response, 'id="service-name-suggestions"')

    def test_service_name_lookup_returns_similar_services(self) -> None:
        create_service(workshop=self.workshop, suffix=12)

        response = self.client.get(
            reverse("catalog:services_search"),
            {
                "name": "Servico 12",
                "target_id": "service-name-suggestions",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Encontramos serviços com nome parecido")
        self.assertContains(response, "Servico 12")
        self.assertContains(response, "service-name-suggestions")


class BudgetQuickCreateServiceValidationTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=97)
        self.budget = create_budget(workshop=self.workshop)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_quick_create_service_shows_duplicate_name_error(self) -> None:
        create_service(workshop=self.workshop, suffix=97)

        response = self.client.post(
            reverse("budget:quick_create_item", args=[self.budget.pk, "service"]),
            {
                "name": "Servico 97",
                "duration": "01:00",
                "selling_price_0": "20.00",
                "selling_price_1": "BRL",
                "modal_context": "parent",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Já existe um serviço com este nome.")
        self.assertEqual(Service.objects.filter(workshop=self.workshop, name="Servico 97").count(), 1)
        self.assertFalse(BudgetItem.objects.filter(budget=self.budget, service__name="Servico 97").exists())

    def test_register_local_service_shows_duplicate_name_error(self) -> None:
        create_service(workshop=self.workshop, suffix=98)
        local_item = BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            description="Servico local 98",
            quantity=1,
            service_cost_price=Money("10.00", "BRL"),
            service_selling_price=Money("20.00", "BRL"),
            duration=timedelta(hours=1),
            is_local=True,
        )

        response = self.client.post(
            reverse("budget:register_local_item", args=[self.budget.pk, local_item.pk]),
            {
                "name": "Servico 98",
                "duration": "01:00",
                "selling_price_0": "20.00",
                "selling_price_1": "BRL",
            },
            HTTP_HX_REQUEST="true",
        )

        local_item.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Retarget"], "#modal-container")
        self.assertContains(response, "Já existe um serviço com este nome.")
        self.assertEqual(Service.objects.filter(workshop=self.workshop, name="Servico 98").count(), 1)
        self.assertTrue(local_item.is_local)
        self.assertIsNone(local_item.service)


class BudgetDuplicateKitProductTests(TestCase):
    def test_step4_kit_price_includes_products_and_services(self) -> None:
        workshop = create_workshop(suffix=87)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=87)
        service = create_service(workshop=workshop, suffix=87)
        kit = create_kit(workshop=workshop, suffix=871, products=[(product, 1)])
        KitService.objects.create(kit=kit, service=service, quantity=1, duration=service.duration)

        kit_item = BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit, quantity=1)

        rows = _render_budget_items_rows(budget, step6=False)

        self.assertIn(str(kit_item.kit_unit_price), rows["kit"])

    @patch.object(Budget, "total_labor_cost_value", new_callable=PropertyMock, return_value=Money("40.00", "BRL"))
    def test_slider_all_to_labor_preserves_product_cost_plus_shipping(self, _labor_cost_mock) -> None:
        workshop = create_workshop(suffix=88)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=88)
        service = create_service(workshop=workshop, suffix=88)

        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=2, shipping=Money("5.00", "BRL"))
        BudgetItem.objects.create(workshop=workshop, budget=budget, service=service, quantity=1)

        budget.slider = 100
        budget.save(update_fields=["slider"])

        self.assertEqual(budget.get_total_products_by_slider, Money("25.00", "BRL"))
        self.assertEqual(budget.get_total_products_by_slider_without_shipping, Money("20.00", "BRL"))

    @patch.object(Budget, "total_labor_cost_value", new_callable=PropertyMock, return_value=Money("40.00", "BRL"))
    def test_slider_all_to_parts_preserves_minimum_labor_sale(self, _labor_cost_mock) -> None:
        workshop = create_workshop(suffix=89)
        budget = create_budget(workshop=workshop)
        service = create_service(workshop=workshop, suffix=89)

        BudgetItem.objects.create(workshop=workshop, budget=budget, service=service, quantity=4)

        budget.slider = -100
        budget.save(update_fields=["slider"])

        self.assertEqual(budget.get_total_labor_by_slider, Money("40.00", "BRL"))

    @patch.object(Budget, "total_labor_cost_value", new_callable=PropertyMock, return_value=Money("20.00", "BRL"))
    def test_pdf_service_profit_stays_at_zero_when_labor_reaches_cost_floor(self, _labor_cost_mock) -> None:
        workshop = create_workshop(suffix=90)
        budget = create_budget(workshop=workshop)
        service_a = create_service(workshop=workshop, suffix=90)
        service_b = create_service(workshop=workshop, suffix=91)

        service_a.duration = timedelta(hours=3)
        service_a.save(update_fields=["duration"])
        service_b.duration = timedelta(hours=1)
        service_b.save(update_fields=["duration"])

        BudgetItem.objects.create(workshop=workshop, budget=budget, service=service_a, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, service=service_b, quantity=1)

        budget.slider = -100
        budget.save(update_fields=["slider"])

        context = build_budget_pdf_context(budget=budget, observacao="Observacao de teste")

        self.assertEqual(context["total_profit_service_value"], Money("0.00", "BRL"))
        self.assertEqual(context["total_servicos"], Money("20.00", "BRL"))
        self.assertEqual(context["servicos"][0]["total_price"], context["servicos"][0]["service_cost_price"])
        self.assertEqual(context["servicos"][0]["profit_value"], Money("0.00", "BRL"))
        self.assertEqual(context["servicos"][1]["total_price"], context["servicos"][1]["service_cost_price"])
        self.assertEqual(context["servicos"][1]["profit_value"], Money("0.00", "BRL"))

    def test_budget_uses_slider_totals_with_duplicate_kit_product_consolidation(self) -> None:
        workshop = create_workshop(suffix=85)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=85, application="Gol")
        service = create_service(workshop=workshop, suffix=85)
        kit_1 = create_kit(workshop=workshop, suffix=851, products=[(product, 2)])
        kit_2 = create_kit(workshop=workshop, suffix=852, products=[(product, 1)])

        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_1, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_2, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, service=service, quantity=1)

        budget.slider = -50
        budget.save(update_fields=["slider"])

        self.assertEqual(budget.total_products_value, Money("45.00", "BRL"))
        self.assertEqual(budget.total_costs_products_value, Money("30.00", "BRL"))
        self.assertEqual(budget.get_total_products_by_slider, Money("52.50", "BRL"))
        self.assertEqual(budget.get_total_services_by_slider, Money("12.50", "BRL"))
        self.assertEqual(budget.total_base_value, Money("65.00", "BRL"))

        context = build_budget_pdf_context(budget=budget, observacao="Observacao de teste")

        self.assertEqual(len(context["produtos"]), 1)
        self.assertEqual(context["produtos"][0]["quantity"], 3)
        self.assertEqual(context["produtos"][0]["total_price"], Money("52.50", "BRL"))
        self.assertEqual(context["servicos"][0]["total_price"], Money("12.50", "BRL"))

    def test_duplicate_product_warning_is_rendered_for_direct_item_present_in_kit(self) -> None:
        workshop = create_workshop(suffix=86)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=86)
        kit = create_kit(workshop=workshop, suffix=861, products=[(product, 2)])

        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=1)

        rows = _render_budget_items_rows(budget, step6=False)

        self.assertIn("Produto já registrado em um kit", rows["product"])

    def test_budget_uses_duplicate_kit_service_consolidation_with_direct_service(self) -> None:
        workshop = create_workshop(suffix=92)
        budget = create_budget(workshop=workshop)
        service = create_service(workshop=workshop, suffix=92)
        kit_1 = create_kit(workshop=workshop, suffix=921, products=[])
        kit_2 = create_kit(workshop=workshop, suffix=922, products=[])
        KitService.objects.create(kit=kit_1, service=service, quantity=2, duration=service.duration)
        KitService.objects.create(kit=kit_2, service=service, quantity=1, duration=service.duration)

        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_1, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_2, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, service=service, quantity=1)

        context = build_budget_pdf_context(budget=budget, observacao="Observacao de teste")

        self.assertEqual(len(context["servicos"]), 1)
        self.assertEqual(context["servicos"][0]["quantity"], 3)
        self.assertEqual(context["servicos"][0]["total_price"], Money("60.00", "BRL"))

    @patch.object(Budget, "calculate_pricing_methods", return_value={"method_name": "Hunter", "venda_mao_obra": Money("3000.00", "BRL")})
    @patch.object(Budget, "total_labor_cost_value", new_callable=PropertyMock, return_value=Money("15.29", "BRL"))
    def test_budget_preserves_kit_service_cost_override_in_pdf_totals(self, _labor_cost_mock, _pricing_methods_mock) -> None:
        workshop = create_workshop(suffix=93)
        budget = create_budget(workshop=workshop)
        service = create_service(workshop=workshop, suffix=93)
        kit = create_kit(workshop=workshop, suffix=931, products=[])
        KitService.objects.create(kit=kit, service=service, quantity=1, duration=service.duration, selling_price=Money("3000.00", "BRL"))

        item = BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit, quantity=1)

        override = BudgetKitItemOverride.objects.get(budget_item=item, service=service)
        override.service_cost_price = Money("2050.00", "BRL")
        override.save(update_fields=["service_cost_price", "service_cost_price_currency"])
        item.refresh_kit_snapshot_totals()
        budget.invalidate_pricing_snapshot_cache()

        context = build_budget_pdf_context(budget=budget, observacao="Observacao de teste")

        self.assertEqual(budget.total_costs_services_value, Money("2050.00", "BRL"))
        self.assertEqual(context["servicos"][0]["service_cost_price"], Money("2050.00", "BRL"))
        self.assertEqual(context["soma_markup_display"], "1,46 vezes")

    def test_budget_duplicate_service_tie_uses_higher_total_source(self) -> None:
        workshop = create_workshop(suffix=923)
        budget = create_budget(workshop=workshop)
        service = create_service(workshop=workshop, suffix=923)
        kit_1 = create_kit(workshop=workshop, suffix=9231, products=[])
        kit_2 = create_kit(workshop=workshop, suffix=9232, products=[])
        KitService.objects.create(kit=kit_1, service=service, quantity=1, duration=service.duration, selling_price=Money("30.00", "BRL"))
        KitService.objects.create(kit=kit_2, service=service, quantity=1, duration=service.duration, selling_price=Money("20.00", "BRL"))

        BudgetItem.objects.create(workshop=workshop, budget=budget, service=service, quantity=2)
        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_1, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_2, quantity=1)

        context = build_budget_pdf_context(budget=budget, observacao="Observacao de teste")

        self.assertEqual(len(context["servicos"]), 1)
        self.assertEqual(context["servicos"][0]["quantity"], 2)
        self.assertEqual(context["servicos"][0]["total_price"], Money("50.00", "BRL"))

    def test_budget_sums_same_service_from_multiple_kits_with_override_price(self) -> None:
        workshop = create_workshop(suffix=920)
        budget = create_budget(workshop=workshop)
        service = create_service(workshop=workshop, suffix=920)
        kit_1 = create_kit(workshop=workshop, suffix=9201, products=[])
        kit_2 = create_kit(workshop=workshop, suffix=9202, products=[])
        kit_3 = create_kit(workshop=workshop, suffix=9203, products=[])

        KitService.objects.create(kit=kit_1, service=service, quantity=1, duration=service.duration, selling_price=Money("20.00", "BRL"))
        KitService.objects.create(kit=kit_2, service=service, quantity=1, duration=service.duration, selling_price=Money("20.00", "BRL"))
        KitService.objects.create(kit=kit_3, service=service, quantity=1, duration=service.duration, selling_price=Money("0.00", "BRL"))

        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_1, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_2, quantity=1)
        kit_item_3 = BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_3, quantity=1)

        override = BudgetKitItemOverride.objects.get(budget_item=kit_item_3, service=service)
        override.service_selling_price = Money("40.00", "BRL")
        override.save(update_fields=["service_selling_price", "service_selling_price_currency"])
        kit_item_3.refresh_kit_snapshot_totals()

        context = build_budget_pdf_context(budget=budget, observacao="Observacao de teste")

        self.assertEqual(budget.total_services_value, Money("80.00", "BRL"))
        self.assertEqual(context["total_servicos"], Money("80.00", "BRL"))
        self.assertEqual(len(context["servicos"]), 1)
        self.assertEqual(context["servicos"][0]["quantity"], 3)
        self.assertEqual(context["servicos"][0]["total_price"], Money("80.00", "BRL"))

    def test_budget_item_uses_kit_service_custom_selling_price(self) -> None:
        workshop = create_workshop(suffix=94)
        budget = create_budget(workshop=workshop)
        service = create_service(workshop=workshop, suffix=94)
        kit = create_kit(workshop=workshop, suffix=941, products=[])
        KitService.objects.create(kit=kit, service=service, quantity=2, duration=service.duration, selling_price=Money("33.00", "BRL"))

        item = BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit, quantity=1)

        self.assertEqual(item.service_selling_price, Money("66.00", "BRL"))
        self.assertEqual(item.get_kit_services_total(), Money("66.00", "BRL"))

    def test_budget_kit_services_match_selected_catalog_column_total(self) -> None:
        workshop = create_workshop(suffix=42)
        budget = create_budget(workshop=workshop)
        service_1 = create_service(workshop=workshop, suffix=42)
        service_2 = create_service(workshop=workshop, suffix=43)
        kit = create_kit(workshop=workshop, suffix=42, products=[])
        kit.service_pricing_mode = Kit.ServicePricingMode.BY_DURATION
        kit.save(update_fields=["service_pricing_mode"])
        KitService.objects.create(kit=kit, service=service_1, quantity=2, duration=timedelta(hours=1), duration_selling_price=Money("31.50", "BRL"), selling_price=Money("99.00", "BRL"))
        KitService.objects.create(kit=kit, service=service_2, quantity=3, duration=timedelta(minutes=30), duration_selling_price=Money("12.25", "BRL"), selling_price=Money("88.00", "BRL"))
        kit.recalculate_total_price()

        item = BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit, quantity=1)
        _, service_overrides = item._get_kit_override_maps()

        self.assertEqual(service_overrides[service_1.pk].service_selling_price, Money("31.50", "BRL"))
        self.assertEqual(service_overrides[service_2.pk].service_selling_price, Money("12.25", "BRL"))
        self.assertEqual(item.get_kit_services_total(), Money("99.75", "BRL"))
        self.assertEqual(item.get_kit_services_total(), kit.total_price)

    def test_budget_item_uses_selected_duration_column_when_workshop_cost_exists(self) -> None:
        workshop = create_workshop(suffix=95)
        budget = create_budget(workshop=workshop)
        service = create_service(workshop=workshop, suffix=95)
        kit = create_kit(workshop=workshop, suffix=951, products=[])
        kit.service_pricing_mode = Kit.ServicePricingMode.BY_DURATION
        kit.save(update_fields=["service_pricing_mode"])
        KitService.objects.create(kit=kit, service=service, quantity=1, duration=timedelta(hours=2), selling_price=Money("33.00", "BRL"))

        reference_date = budget.criado_em if budget.criado_em else timezone.now()
        WorkshopCost.objects.create(
            workshop=workshop,
            month=reference_date.month,
            year=reference_date.year,
            mechanic_quantity=1,
            minimum_hourly_cost=Money("30.00", "BRL"),
            hourly_cost_value=Money("80.00", "BRL"),
        )

        item = BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit, quantity=1)

        self.assertEqual(item.service_cost_price, Money("60.00", "BRL"))
        self.assertEqual(item.service_selling_price, Money("33.00", "BRL"))

    def test_budget_item_duration_mode_falls_back_to_inserted_value_without_workshop_cost(self) -> None:
        workshop = create_workshop(suffix=96)
        budget = create_budget(workshop=workshop)
        service = create_service(workshop=workshop, suffix=96)
        kit = create_kit(workshop=workshop, suffix=961, products=[])
        kit.service_pricing_mode = Kit.ServicePricingMode.BY_DURATION
        kit.save(update_fields=["service_pricing_mode"])
        KitService.objects.create(kit=kit, service=service, quantity=1, duration=timedelta(hours=2), selling_price=Money("45.00", "BRL"))

        item = BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit, quantity=1)

        self.assertEqual(item.service_selling_price, Money("45.00", "BRL"))

    def test_budget_item_inserted_mode_uses_inserted_value_even_with_workshop_cost(self) -> None:
        workshop = create_workshop(suffix=97)
        budget = create_budget(workshop=workshop)
        service = create_service(workshop=workshop, suffix=97)
        kit = create_kit(workshop=workshop, suffix=971, products=[])
        kit.service_pricing_mode = Kit.ServicePricingMode.INSERTED_VALUE
        kit.save(update_fields=["service_pricing_mode"])
        KitService.objects.create(kit=kit, service=service, quantity=1, duration=timedelta(hours=2), selling_price=Money("55.00", "BRL"))

        reference_date = budget.criado_em if budget.criado_em else timezone.now()
        WorkshopCost.objects.create(
            workshop=workshop,
            month=reference_date.month,
            year=reference_date.year,
            mechanic_quantity=1,
            minimum_hourly_cost=Money("25.00", "BRL"),
            hourly_cost_value=Money("90.00", "BRL"),
        )

        item = BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit, quantity=1)

        self.assertEqual(item.service_cost_price, Money("50.00", "BRL"))
        self.assertEqual(item.service_selling_price, Money("55.00", "BRL"))

    def test_budget_item_uses_manual_kit_service_cost_when_present(self) -> None:
        workshop = create_workshop(suffix=98)
        budget = create_budget(workshop=workshop)
        service = create_service(workshop=workshop, suffix=98)
        kit = create_kit(workshop=workshop, suffix=981, products=[])
        kit.service_pricing_mode = Kit.ServicePricingMode.BY_DURATION
        kit.save(update_fields=["service_pricing_mode"])
        KitService.objects.create(kit=kit, service=service, quantity=1, duration=timedelta(hours=2), cost_price=Money("77.00", "BRL"), selling_price=Money("55.00", "BRL"))

        reference_date = budget.criado_em if budget.criado_em else timezone.now()
        WorkshopCost.objects.create(
            workshop=workshop,
            month=reference_date.month,
            year=reference_date.year,
            mechanic_quantity=1,
            minimum_hourly_cost=Money("25.00", "BRL"),
            hourly_cost_value=Money("90.00", "BRL"),
        )

        item = BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit, quantity=1)

        self.assertEqual(item.service_cost_price, Money("77.00", "BRL"))
        self.assertEqual(item.service_selling_price, Money("55.00", "BRL"))

    def test_budget_item_uses_manual_kit_service_duration_selling_when_present(self) -> None:
        workshop = create_workshop(suffix=99)
        budget = create_budget(workshop=workshop)
        service = create_service(workshop=workshop, suffix=99)
        kit = create_kit(workshop=workshop, suffix=991, products=[])
        kit.service_pricing_mode = Kit.ServicePricingMode.BY_DURATION
        kit.save(update_fields=["service_pricing_mode"])
        KitService.objects.create(
            kit=kit,
            service=service,
            quantity=1,
            duration=timedelta(hours=2),
            duration_selling_price=Money("210.00", "BRL"),
            selling_price=Money("55.00", "BRL"),
        )

        reference_date = budget.criado_em if budget.criado_em else timezone.now()
        WorkshopCost.objects.create(
            workshop=workshop,
            month=reference_date.month,
            year=reference_date.year,
            mechanic_quantity=1,
            minimum_hourly_cost=Money("25.00", "BRL"),
            hourly_cost_value=Money("90.00", "BRL"),
        )

        item = BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit, quantity=1)

        self.assertEqual(item.service_selling_price, Money("210.00", "BRL"))

    def test_budget_item_freezes_kit_values_after_creation(self) -> None:
        workshop = create_workshop(suffix=10)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=110)
        service = create_service(workshop=workshop, suffix=110)
        kit = create_kit(workshop=workshop, suffix=101, products=[(product, 2)])
        kit.service_pricing_mode = Kit.ServicePricingMode.INSERTED_VALUE
        kit.save(update_fields=["service_pricing_mode"])
        kit_service = KitService.objects.create(kit=kit, service=service, quantity=1, duration=service.duration, selling_price=Money("85.00", "BRL"))

        item = BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit, quantity=1)
        original_total = item.total_price

        self.assertTrue(item.kit_snapshot_frozen)
        self.assertEqual(BudgetKitItemOverride.objects.filter(budget_item=item, product=product).count(), 1)
        self.assertEqual(BudgetKitItemOverride.objects.filter(budget_item=item, service=service).count(), 1)
        self.assertEqual(original_total, Money("115.00", "BRL"))

        product.selling_price = Money("99.00", "BRL")
        product.cost_price = Money("50.00", "BRL")
        product.save(update_fields=["selling_price", "selling_price_currency", "cost_price", "cost_price_currency"])
        kit.service_pricing_mode = Kit.ServicePricingMode.BY_DURATION
        kit.save(update_fields=["service_pricing_mode"])
        kit_service.selling_price = Money("140.00", "BRL")
        kit_service.duration_selling_price = Money("210.00", "BRL")
        kit_service.cost_price = Money("70.00", "BRL")
        kit_service.save(update_fields=["selling_price", "selling_price_currency", "duration_selling_price", "duration_selling_price_currency", "cost_price", "cost_price_currency"])

        item.refresh_from_db()
        item._clear_kit_snapshot_caches()

        self.assertEqual(item.total_price, original_total)
        self.assertEqual(item.get_kit_products_total(), Money("30.00", "BRL"))
        self.assertEqual(item.get_kit_services_total(), Money("85.00", "BRL"))
        self.assertEqual(item.kit_unit_cost, Money("25.00", "BRL"))

    def test_duplicate_service_warning_is_rendered_for_direct_item_present_in_kit(self) -> None:
        workshop = create_workshop(suffix=93)
        budget = create_budget(workshop=workshop)
        service = create_service(workshop=workshop, suffix=93)
        kit = create_kit(workshop=workshop, suffix=931, products=[])
        KitService.objects.create(kit=kit, service=service, quantity=2, duration=service.duration)

        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, service=service, quantity=1)

        rows = _render_budget_items_rows(budget, step6=False)

        self.assertIn("Serviço já registrado em um kit", rows["service"])


class BudgetKitServiceCalculateViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=83)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.budget = create_budget(workshop=self.workshop)
        self.service = create_service(workshop=self.workshop, suffix=83)
        self.kit = create_kit(workshop=self.workshop, suffix=831, products=[])
        self.kit.service_pricing_mode = Kit.ServicePricingMode.INSERTED_VALUE
        self.kit.save(update_fields=["service_pricing_mode"])
        self.kit_service = KitService.objects.create(kit=self.kit, service=self.service, quantity=1, duration=timedelta(hours=1), selling_price=Money("55.00", "BRL"))

        reference_date = self.budget.criado_em if self.budget.criado_em else timezone.now()
        WorkshopCost.objects.create(
            workshop=self.workshop,
            month=reference_date.month,
            year=reference_date.year,
            mechanic_quantity=1,
            minimum_hourly_cost=Money("25.00", "BRL"),
            hourly_cost_value=Money("90.00", "BRL"),
        )

        self.item = BudgetItem.objects.create(workshop=self.workshop, budget=self.budget, kit=self.kit, quantity=1)

    def test_duration_change_preserves_selected_inserted_service_price(self) -> None:
        response = self.client.post(
            reverse("budget:calculate_kit_service", args=[self.budget.pk, self.item.pk, self.service.pk]),
            data={
                "changed_field": "duration",
                "duration": "02:00:00",
                "quantity": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        override = BudgetKitItemOverride.objects.get(budget_item=self.item, service=self.service)
        self.item.refresh_from_db()

        self.assertEqual(payload["price"], "55.00")
        self.assertEqual(override.service_selling_price, Money("55.00", "BRL"))
        self.assertEqual(override.service_cost_price, Money("50.00", "BRL"))
        self.assertEqual(override.duration, timedelta(hours=2))
        self.assertEqual(self.item.service_selling_price, Money("55.00", "BRL"))

    def test_duration_change_without_workshop_cost_uses_frozen_budget_snapshot(self) -> None:
        WorkshopCost.objects.filter(workshop=self.workshop).delete()

        response = self.client.post(
            reverse("budget:calculate_kit_service", args=[self.budget.pk, self.item.pk, self.service.pk]),
            data={
                "changed_field": "duration",
                "duration": "02:00:00",
                "quantity": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        override = BudgetKitItemOverride.objects.get(budget_item=self.item, service=self.service)

        self.assertFalse(payload["workshop_cost_missing"])
        self.assertEqual(payload["price"], "55.00")
        self.assertEqual(override.service_selling_price, Money("55.00", "BRL"))
        self.assertEqual(override.service_cost_price, Money("50.00", "BRL"))

    def test_duration_change_without_pricing_context_keeps_registered_kit_service_value(self) -> None:
        WorkshopCost.objects.filter(workshop=self.workshop).delete()
        budget = create_budget(workshop=self.workshop)
        service = create_service(workshop=self.workshop, suffix=84)
        kit = create_kit(workshop=self.workshop, suffix=841, products=[])
        kit.service_pricing_mode = Kit.ServicePricingMode.BY_DURATION
        kit.save(update_fields=["service_pricing_mode"])
        KitService.objects.create(kit=kit, service=service, quantity=2, duration=timedelta(hours=1), selling_price=Money("55.00", "BRL"))
        item = BudgetItem.objects.create(workshop=self.workshop, budget=budget, kit=kit, quantity=1)

        response = self.client.post(
            reverse("budget:calculate_kit_service", args=[budget.pk, item.pk, service.pk]),
            data={
                "changed_field": "duration",
                "duration": "02:00:00",
                "quantity": "2",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        override = BudgetKitItemOverride.objects.get(budget_item=item, service=service)
        item.refresh_from_db()

        self.assertTrue(payload["workshop_cost_missing"])
        self.assertEqual(payload["price"], "55.00")
        self.assertEqual(override.service_selling_price, Money("55.00", "BRL"))
        self.assertEqual(item.service_selling_price, Money("110.00", "BRL"))

    def test_kit_edit_modal_uses_frontend_totals_without_autosave(self) -> None:
        response = self.client.get(reverse("budget:edit_kit", args=[self.budget.pk, self.item.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="products-total-display"')
        self.assertContains(response, 'id="services-total-display"')
        self.assertContains(response, "updateProductTotals")
        self.assertContains(response, "updateServiceTotals")
        self.assertContains(response, "recalculateServicePricingFromDuration")
        self.assertContains(response, "minimumHourlyCost: parseFloat('25.00')")
        self.assertContains(response, "hourlyCostValue: parseFloat('90.00')")
        self.assertNotContains(response, "/calculate/")
        self.assertNotContains(response, "debounce")

    def test_kit_edit_modal_save_returns_json_redirect_for_fetch(self) -> None:
        response = self.client.post(
            reverse("budget:edit_kit", args=[self.budget.pk, self.item.pk]),
            data={
                "products": "[]",
                "services": json.dumps(
                    [
                        {
                            "id": self.service.pk,
                            "quantity": 1,
                            "cost": "25.00",
                            "price": "55.00",
                            "duration": "01:00:00",
                        }
                    ]
                ),
            },
            HTTP_ACCEPT="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertNotIn("HX-Redirect", response)
        self.assertJSONEqual(response.content, {"ok": True, "redirect_url": f"/budget/{self.budget.pk}/edit/?step=4"})


class BudgetPricingSnapshotTests(TestCase):
    def test_budget_snapshot_preserves_old_values_after_workshop_cost_change(self) -> None:
        workshop = create_workshop(suffix=11)
        budget = create_budget(workshop=workshop)
        mechanic_cost, _ = create_salary_monthly_costs(workshop=workshop)
        reference_date = budget.criado_em if budget.criado_em else timezone.now()

        workshop_cost = WorkshopCost.objects.create(
            workshop=workshop,
            month=reference_date.month,
            year=reference_date.year,
            mechanic_quantity=1,
            working_hours_per_month=Decimal("100.00"),
            minimum_hourly_cost=Money("30.00", "BRL"),
            hourly_cost_value=Money("80.00", "BRL"),
            profitability_multiplier=Decimal("2.50"),
        )
        WorkshopCostItem.objects.create(workshop_cost=workshop_cost, monthly_cost=mechanic_cost, amount=Money("1000.00", "BRL"))

        budget.freeze_pricing_snapshot()

        WorkshopCostItem.objects.filter(workshop_cost=workshop_cost, monthly_cost=mechanic_cost).update(amount=Money("2000.00", "BRL"))
        WorkshopCost.objects.filter(pk=workshop_cost.pk).update(
            working_hours_per_month=Decimal("200.00"),
            minimum_hourly_cost=Money("40.00", "BRL"),
            hourly_cost_value=Money("120.00", "BRL"),
            profitability_multiplier=Decimal("3.00"),
        )
        budget.refresh_from_db()

        self.assertEqual(budget.pricing_productive_salary_total, Money("1000.00", "BRL"))
        self.assertEqual(budget.mechanic_hour_cost_value, Money("10.00", "BRL"))
        self.assertEqual(budget.get_mlr, Decimal("2.50"))

    def test_budget_get_mlr_and_get_mlo_fall_back_to_live_workshop_cost_when_snapshot_is_empty(self) -> None:
        workshop = create_workshop(suffix=13)
        budget = create_budget(workshop=workshop)
        mechanic_cost, _ = create_salary_monthly_costs(workshop=workshop)
        reference_date = budget.criado_em if budget.criado_em else timezone.now()

        workshop_cost = WorkshopCost.objects.create(
            workshop=workshop,
            month=reference_date.month,
            year=reference_date.year,
            mechanic_quantity=1,
            working_hours_per_month=Decimal("100.00"),
            minimum_hourly_cost=Money("30.00", "BRL"),
            hourly_cost_value=Money("80.00", "BRL"),
            profitability_multiplier=Decimal("2.50"),
        )
        WorkshopCostItem.objects.create(workshop_cost=workshop_cost, monthly_cost=mechanic_cost, amount=Money("1000.00", "BRL"))

        Budget.objects.filter(pk=budget.pk).update(
            pricing_reference_month=reference_date.month,
            pricing_reference_year=reference_date.year,
            pricing_productive_salary_total=Money("0.00", "BRL"),
            pricing_working_hours_per_month=Decimal("0.00"),
            pricing_minimum_hourly_cost=Money("0.00", "BRL"),
            pricing_hourly_cost_value=Money("0.00", "BRL"),
            pricing_profitability_multiplier=Decimal("0.00"),
        )
        budget.refresh_from_db()

        self.assertEqual(budget.get_mlr, Decimal("2.50"))
        self.assertEqual(budget.get_mlo, Decimal("1.00"))


class CollaboratorSalarySyncTests(TestCase):
    def test_new_collaborator_updates_current_month_and_preserves_existing_budget_and_workorder(self) -> None:
        _, workshop = create_director_user_with_workshop(suffix=12)
        mechanic_cost, admin_cost = create_salary_monthly_costs(workshop=workshop)
        today = timezone.localdate()
        workshop_cost = WorkshopCost.objects.create(
            workshop=workshop,
            month=today.month,
            year=today.year,
            mechanic_quantity=1,
            work_hours_per_day=timedelta(hours=10),
            work_days_per_month=20,
            productivity_average=Decimal("0.50"),
            working_hours_per_month=Decimal("100.00"),
            minimum_hourly_cost=Money("10.00", "BRL"),
            hourly_cost_value=Money("20.00", "BRL"),
            profitability_multiplier=Decimal("2.00"),
        )
        WorkshopCostItem.objects.create(workshop_cost=workshop_cost, monthly_cost=mechanic_cost, amount=Money("1000.00", "BRL"))
        WorkshopCostItem.objects.create(workshop_cost=workshop_cost, monthly_cost=admin_cost, amount=Money("500.00", "BRL"))

        previous_budget = create_budget(workshop=workshop)
        previous_workorder = WorkOrder.objects.create(workshop=workshop, budget=previous_budget)

        collaborator = WorkshopCollaborator.objects.create(
            workshop=workshop,
            name="Novo Produtivo",
            cpf="52998224725",
            birth_date=today,
            position="Mecanico",
            salary=Money("500.00", "BRL"),
            admission_date=today,
            collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
            is_active=True,
        )

        freeze_existing_pricing_history(workshop=workshop, cutoff=collaborator.criado_em)
        sync_current_month_salary_costs(workshop=workshop)

        workshop_cost.refresh_from_db()
        previous_budget.refresh_from_db()
        previous_workorder.refresh_from_db()

        mechanic_item = WorkshopCostItem.objects.get(workshop_cost=workshop_cost, monthly_cost=mechanic_cost)
        self.assertEqual(mechanic_item.amount, Money("500.00", "BRL"))
        self.assertEqual(previous_budget.pricing_productive_salary_total, Money("1000.00", "BRL"))
        self.assertEqual(previous_budget.mechanic_hour_cost_value, Money("10.00", "BRL"))
        self.assertEqual(previous_workorder.mechanic_hour_cost_value, Money("10.00", "BRL"))

        future_budget = create_budget(workshop=workshop)

        self.assertEqual(future_budget.mechanic_hour_cost_value, Money("5.00", "BRL"))


class BudgetSignaturePublicViewTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @patch("apps.budget.views.pdf_views.render")
    @patch("apps.budget.views.pdf_views.build_budget_pdf_context")
    def test_signature_preview_renders_budget_pdf_template(self, build_context_mock, render_mock) -> None:
        workshop = create_workshop(suffix=78)
        budget = create_budget(workshop=workshop)
        token = extract_token_from_url(build_signature_preview_url(budget=budget))

        build_context_mock.return_value = {"budget": budget, "fixed_observation": workshop.pdf_observation}
        render_mock.return_value = HttpResponse("preview")

        response = signature_preview(self.factory.get("/"), token)

        self.assertEqual(response.content, b"preview")
        render_mock.assert_called_once()
        self.assertEqual(render_mock.call_args.args[1], "budget/partials/pdf/visualizarPDF.html")
        self.assertEqual(render_mock.call_args.args[2], {"budget": budget, "fixed_observation": workshop.pdf_observation})
        build_context_mock.assert_called_once_with(budget=budget, request=ANY, zero_warranty_prices=True, presentation="selected_items")

    def test_signature_preview_rejects_inactive_token(self) -> None:
        workshop = create_workshop(suffix=79)
        budget = create_budget(workshop=workshop)
        budget.revoke_signature_token()
        token = extract_token_from_url(build_signature_preview_url(budget=budget))

        with self.assertRaises(Http404):
            signature_preview(self.factory.get("/"), token)

    @patch("apps.budget.views.pdf_views.render_budget_pdf_document")
    def test_signature_file_returns_inline_pdf(self, render_document_mock) -> None:
        workshop = create_workshop(suffix=80)
        budget = create_budget(workshop=workshop)
        token = extract_token_from_url(build_signature_file_url(budget=budget))

        render_document_mock.return_value = DocumentPayload(
            content=b"%PDF-file",
            filename=f"orcamento_{budget.id}.pdf",
        )

        response = signature_file(self.factory.get("/"), token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-file")
        self.assertIn('inline; filename="orcamento_', response["Content-Disposition"])


class BudgetSignatureInternalPdfTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @patch("apps.budget.views.pdf_views.get_active_workshop_or_404")
    @patch("apps.budget.views.pdf_views.render_budget_pdf_document")
    @patch("apps.budget.views.pdf_views.download_signed_document_content")
    def test_visualizar_pdf_assinatura_variant_base_skips_signed_download(self, download_signed_mock, render_document_mock, active_workshop_mock) -> None:
        workshop = create_workshop(suffix=1)
        budget = create_budget(workshop=workshop)
        budget.signature_request_status = SignatureStatus.APPROVED
        budget.signature_external_id = "env-1"
        budget.signature_document_id = "doc-1"
        budget.save(update_fields=["signature_request_status", "signature_external_id", "signature_document_id"])

        active_workshop_mock.return_value = workshop
        render_document_mock.return_value = DocumentPayload(
            content=b"%PDF-base-only",
            filename=f"orcamento_{budget.id}_base.pdf",
        )

        response = visualizar_pdf_assinatura(self.factory.get("/", {"variant": "base", "download": "1"}), budget.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-base-only")
        self.assertIn("attachment;", response["Content-Disposition"])
        download_signed_mock.assert_not_called()
        render_document_mock.assert_called_once()

    @patch("apps.budget.views.pdf_views.get_active_workshop_or_404")
    @patch("apps.budget.views.pdf_views.download_signed_document_content")
    def test_visualizar_pdf_assinatura_returns_signed_pdf_when_available(self, download_signed_mock, active_workshop_mock) -> None:
        workshop = create_workshop(suffix=81)
        budget = create_budget(workshop=workshop)
        budget.signature_request_status = SignatureStatus.APPROVED
        budget.signature_external_id = "env-81"
        budget.signature_document_id = "doc-81"
        budget.save(update_fields=["signature_request_status", "signature_external_id", "signature_document_id"])

        active_workshop_mock.return_value = workshop
        download_signed_mock.return_value = b"%PDF-signed"

        request = self.factory.get("/", {"download": "1"})
        response = visualizar_pdf_assinatura(request, budget.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-signed")
        self.assertIn("attachment;", response["Content-Disposition"])
        download_signed_mock.assert_called_once_with(document_id="doc-81", envelope_id="env-81")

    @patch("apps.budget.views.pdf_views.get_active_workshop_or_404")
    @patch("apps.budget.views.pdf_views.render_budget_pdf_document")
    @patch("apps.budget.views.pdf_views.download_signed_document_content")
    def test_visualizar_pdf_assinatura_falls_back_to_base_pdf(self, download_signed_mock, render_document_mock, active_workshop_mock) -> None:
        workshop = create_workshop(suffix=82)
        budget = create_budget(workshop=workshop)
        budget.signature_request_status = SignatureStatus.APPROVED
        budget.signature_external_id = "env-82"
        budget.save(update_fields=["signature_request_status", "signature_external_id"])

        active_workshop_mock.return_value = workshop
        download_signed_mock.side_effect = SignatureDeliveryServiceError("erro")
        render_document_mock.return_value = DocumentPayload(
            content=b"%PDF-base",
            filename=f"orcamento_{budget.id}_base.pdf",
        )

        response = visualizar_pdf_assinatura(self.factory.get("/"), budget.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-base")
        self.assertIn('inline; filename="orcamento_', response["Content-Disposition"])
        download_signed_mock.assert_called_once_with(document_id=None, envelope_id="env-82")


class BudgetSignatureWorkflowTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @patch("apps.budget.views.workflow_views.send_budget_for_signature")
    def test_trigger_signature_send_if_needed_marks_budget_sent(self, send_signature_mock) -> None:
        workshop = create_workshop(suffix=83)
        budget = create_budget(workshop=workshop)
        send_signature_mock.return_value = SignatureDeliveryResult(
            envelope_id="env-83",
            document_id="doc-83",
            provider="supersign",
            raw_response={"ok": True},
        )

        toast_type, _, redirect_url = trigger_signature_send_if_needed(request=self.factory.post("/"), budget=budget)

        budget.refresh_from_db()
        self.assertEqual(toast_type, "success")
        self.assertEqual(budget.signature_request_status, SignatureStatus.SENT)
        self.assertEqual(budget.signature_external_id, "env-83")
        self.assertEqual(budget.signature_document_id, "doc-83")
        self.assertEqual(redirect_url, reverse("budget:budget_list"))

    @patch("apps.budget.views.workflow_views.send_budget_for_signature")
    def test_trigger_signature_send_if_needed_allows_resend_when_already_sent(self, send_signature_mock) -> None:
        workshop = create_workshop(suffix=31)
        budget = create_budget(workshop=workshop)
        budget.signature_request_status = SignatureStatus.SENT
        budget.signature_external_id = "env-old-831"
        budget.signature_document_id = "doc-old-831"
        budget.save(update_fields=["signature_request_status", "signature_external_id", "signature_document_id"])
        send_signature_mock.return_value = SignatureDeliveryResult(
            envelope_id="env-new-831",
            document_id="doc-new-831",
            provider="supersign",
            raw_response={"ok": True},
        )

        toast_type, toast_message, redirect_url = trigger_signature_send_if_needed(request=self.factory.post("/"), budget=budget)

        budget.refresh_from_db()
        self.assertEqual(toast_type, "success")
        self.assertEqual(toast_message, "Documento reenviado para assinatura do cliente.")
        self.assertEqual(budget.signature_request_status, SignatureStatus.SENT)
        self.assertEqual(budget.signature_external_id, "env-new-831")
        self.assertEqual(budget.signature_document_id, "doc-new-831")
        self.assertEqual(redirect_url, reverse("budget:budget_list"))

    def test_trigger_signature_send_if_needed_keeps_sending_lock(self) -> None:
        workshop = create_workshop(suffix=32)
        budget = create_budget(workshop=workshop)
        budget.signature_request_status = SignatureStatus.SENDING
        budget.save(update_fields=["signature_request_status"])

        toast_type, toast_message, redirect_url = trigger_signature_send_if_needed(request=self.factory.post("/"), budget=budget)

        budget.refresh_from_db()
        self.assertEqual(toast_type, "info")
        self.assertEqual(toast_message, "O envio do orçamento ainda está em processamento.")
        self.assertEqual(budget.signature_request_status, SignatureStatus.SENDING)
        self.assertIsNone(redirect_url)

    @patch("apps.budget.views.workflow_views.send_budget_for_signature")
    def test_trigger_signature_send_if_needed_marks_budget_failed_on_error(self, send_signature_mock) -> None:
        workshop = create_workshop(suffix=84)
        budget = create_budget(workshop=workshop)
        send_signature_mock.side_effect = SuperSignError("erro")

        toast_type, _, redirect_url = trigger_signature_send_if_needed(request=self.factory.post("/"), budget=budget)

        budget.refresh_from_db()
        self.assertEqual(toast_type, "error")
        self.assertEqual(budget.signature_request_status, SignatureStatus.FAILED)
        self.assertIsNone(redirect_url)


class SuperSignDownloadUrlTests(TestCase):
    @patch("apps.core.documents.gateways.supersign.requests.get")
    def test_returns_download_url_from_supersign_payload(self, requests_get) -> None:
        response = requests_get.return_value
        response.raise_for_status.return_value = None
        response.json.return_value = {"downloadUrl": "https://files.example.com/signed.pdf"}

        with self.settings(
            SUPERSIGN_BASE_URL="https://api.sign.supersign.com.br",
            SUPERSIGN_ACCOUNT_ID="acc-1",
            SUPERSIGN_API_KEY="secret",
        ):
            download_url = get_signed_document_url(document_id="doc-999")

        self.assertEqual(download_url, "https://files.example.com/signed.pdf")
        requests_get.assert_called_once()
        _, kwargs = requests_get.call_args
        self.assertEqual(kwargs["params"], {"type": "signed"})
        self.assertIn("headers", kwargs)
        self.assertEqual(kwargs["headers"]["x-account-id"], "acc-1")
        self.assertNotIn("Authorization", kwargs["headers"])

    @patch("apps.core.documents.gateways.supersign.requests.get")
    def test_retries_with_authorization_when_download_endpoint_requires_jwt(self, requests_get) -> None:
        unauthorized_response = requests.Response()
        unauthorized_response.status_code = 401
        unauthorized_response._content = b'{"error":{"code":"MISSING_JWT","message":"JSON Web Token is missing"}}'

        authorized_response = requests.Response()
        authorized_response.status_code = 200
        authorized_response._content = b'{"downloadUrl": "https://files.example.com/signed.pdf"}'

        requests_get.side_effect = [
            requests.HTTPError("missing jwt", response=unauthorized_response),
            authorized_response,
        ]

        authorized_response.raise_for_status = lambda: None

        with self.settings(
            SUPERSIGN_BASE_URL="https://api.sign.supersign.com.br",
            SUPERSIGN_ACCOUNT_ID="acc-1",
            SUPERSIGN_API_KEY="secret",
        ):
            download_url = get_signed_document_url(document_id="doc-999")

        self.assertEqual(download_url, "https://files.example.com/signed.pdf")
        self.assertEqual(requests_get.call_count, 2)
        first_call = requests_get.call_args_list[0].kwargs
        second_call = requests_get.call_args_list[1].kwargs
        self.assertEqual(first_call["params"], {"type": "signed"})
        self.assertEqual(second_call["params"], {"type": "signed"})
        self.assertNotIn("Authorization", first_call["headers"])
        self.assertEqual(second_call["headers"]["Authorization"], "Bearer secret")

    @patch("apps.core.documents.gateways.supersign.requests.get")
    def test_raises_when_download_url_is_missing(self, requests_get) -> None:
        response = requests_get.return_value
        response.raise_for_status.return_value = None
        response.json.return_value = {"foo": "bar"}

        with self.settings(
            SUPERSIGN_BASE_URL="https://api.sign.supersign.com.br",
            SUPERSIGN_ACCOUNT_ID="acc-1",
            SUPERSIGN_API_KEY="secret",
        ):
            with self.assertRaises(SignatureDeliveryServiceError):
                get_signed_document_url(document_id="doc-999")


class BudgetObservationsFieldTests(TestCase):
    def test_new_budget_has_empty_observations_by_default(self) -> None:
        workshop = create_workshop(suffix=50)
        budget = create_budget(workshop=workshop)
        self.assertEqual(budget.observations, "")

    def test_save_budget_with_observations_persists(self) -> None:
        workshop = create_workshop(suffix=51)
        budget = create_budget(workshop=workshop)
        budget.observations = "Texto de observação de teste."
        budget.save(update_fields=["observations"])
        budget.refresh_from_db()
        self.assertEqual(budget.observations, "Texto de observação de teste.")

    def test_existing_budget_observations_remain_empty(self) -> None:
        workshop = create_workshop(suffix=52)
        budget = create_budget(workshop=workshop)
        budget.refresh_from_db()
        self.assertEqual(budget.observations, "")


class BudgetObservationsFormInitialTests(TestCase):
    def test_step6_form_includes_observations_field(self) -> None:
        workshop = create_workshop(suffix=53)
        budget = create_budget(workshop=workshop)
        request = RequestFactory().get("/")
        request.user = User.objects.create_user(username="obs-form-53", password="123")
        form = BudgetStep6Form(instance=budget, workshop=workshop, request=request)
        self.assertIn("observations", form.fields)

    def test_step6_form_observations_not_required(self) -> None:
        workshop = create_workshop(suffix=54)
        budget = create_budget(workshop=workshop)
        request = RequestFactory().get("/")
        request.user = User.objects.create_user(username="obs-form-54", password="123")
        form = BudgetStep6Form(instance=budget, workshop=workshop, request=request)
        self.assertFalse(form.fields["observations"].required)

    def test_step6_form_renders_observations_field(self) -> None:
        workshop = create_workshop(suffix=55)
        budget = create_budget(workshop=workshop)
        request = RequestFactory().get("/")
        request.user = User.objects.create_user(username="obs-form-55", password="123")
        form = BudgetStep6Form(instance=budget, workshop=workshop, request=request)
        html = Template("{% load crispy_forms_tags %}{% crispy form %}").render(Context({"form": form, "csrf_token": "token"}))
        self.assertIn("observations", html)
        self.assertIn("Observações", html)

    def test_step6_form_shows_existing_observations(self) -> None:
        workshop = create_workshop(suffix=56)
        budget = create_budget(workshop=workshop)
        budget.observations = "Observação existente."
        budget.save(update_fields=["observations"])
        request = RequestFactory().get("/")
        request.user = User.objects.create_user(username="obs-form-56", password="123")
        form = BudgetStep6Form(instance=budget, workshop=workshop, request=request)
        self.assertEqual(form.initial.get("observations"), "Observação existente.")


class BudgetObservationsPreFillTests(TestCase):
    def test_no_previous_budget_initial_is_empty(self) -> None:
        workshop = create_workshop(suffix=57)
        request = RequestFactory().get("/?step=6")
        request.user = User.objects.create_user(username="obs-prefill-57", password="123")
        view = BudgetCreateView()
        view.request = request
        view.workshop = workshop
        view.kwargs = {}
        view._model_instance = None
        kwargs = view.get_form_kwargs()
        self.assertNotIn("observations", kwargs.get("initial", {}))

    def test_previous_budget_in_same_workshop_prefills_observations(self) -> None:
        workshop = create_workshop(suffix=58)
        older_budget = create_budget(workshop=workshop)
        older_budget.observations = "Observação do orçamento anterior."
        older_budget.save(update_fields=["observations"])

        request = RequestFactory().get("/?step=6")
        request.user = User.objects.create_user(username="obs-prefill-58", password="123")
        view = BudgetCreateView()
        view.request = request
        view.workshop = workshop
        view.kwargs = {}
        view._model_instance = None
        kwargs = view.get_form_kwargs()
        self.assertEqual(kwargs["initial"]["observations"], "Observação do orçamento anterior.")

    def test_previous_budget_in_other_workshop_does_not_prefill(self) -> None:
        other_workshop = create_workshop(suffix=59)
        other_budget = create_budget(workshop=other_workshop)
        other_budget.observations = "Observação de outra oficina."
        other_budget.save(update_fields=["observations"])

        current_workshop = create_workshop(suffix=60)

        request = RequestFactory().get("/?step=6")
        request.user = User.objects.create_user(username="obs-prefill-60", password="123")
        view = BudgetCreateView()
        view.request = request
        view.workshop = current_workshop
        view.kwargs = {}
        view._model_instance = None
        kwargs = view.get_form_kwargs()
        self.assertNotIn("observations", kwargs.get("initial", {}))

    def test_most_recent_observation_is_used_for_prefill(self) -> None:
        workshop = create_workshop(suffix=61)
        older = create_budget(workshop=workshop)
        older.observations = "Observação antiga."
        older.save(update_fields=["observations"])

        newer = create_budget(workshop=workshop)
        newer.observations = "Observação mais recente."
        newer.save(update_fields=["observations"])

        request = RequestFactory().get("/?step=6")
        request.user = User.objects.create_user(username="obs-prefill-61", password="123")
        view = BudgetCreateView()
        view.request = request
        view.workshop = workshop
        view.kwargs = {}
        view._model_instance = None
        kwargs = view.get_form_kwargs()
        self.assertEqual(kwargs["initial"]["observations"], "Observação mais recente.")

    def test_empty_observations_are_skipped_for_prefill(self) -> None:
        workshop = create_workshop(suffix=62)
        first = create_budget(workshop=workshop)
        first.observations = "Observação com texto."
        first.save(update_fields=["observations"])

        second = create_budget(workshop=workshop)
        second.observations = ""
        second.save(update_fields=["observations"])

        request = RequestFactory().get("/?step=6")
        request.user = User.objects.create_user(username="obs-prefill-62", password="123")
        view = BudgetCreateView()
        view.request = request
        view.workshop = workshop
        view.kwargs = {}
        view._model_instance = None
        kwargs = view.get_form_kwargs()
        self.assertEqual(kwargs["initial"]["observations"], "Observação com texto.")

    def test_existing_budget_does_not_get_prefill(self) -> None:
        workshop = create_workshop(suffix=63)
        existing_budget = create_budget(workshop=workshop)
        existing_budget.observations = ""
        existing_budget.save(update_fields=["observations"])

        previous = create_budget(workshop=workshop)
        previous.observations = "Observação anterior."
        previous.save(update_fields=["observations"])

        request = RequestFactory().get(f"/?step=6&pk={existing_budget.pk}")
        request.user = User.objects.create_user(username="obs-prefill-63", password="123")
        view = BudgetCreateView()
        view.request = request
        view.workshop = workshop
        view.kwargs = {"pk": existing_budget.pk}
        view._model_instance = existing_budget
        kwargs = view.get_form_kwargs()
        self.assertNotIn("observations", kwargs.get("initial", {}))


class BudgetObservationsPdfContextTests(TestCase):
    def test_pdf_context_includes_observations(self) -> None:
        workshop = create_workshop(suffix=64)
        budget = create_budget(workshop=workshop)
        budget.observations = "Observação para o PDF."
        budget.save(update_fields=["observations"])
        context = build_budget_pdf_context(budget=budget)
        self.assertEqual(context["observations"], "Observação para o PDF.")

    def test_pdf_context_observations_empty_when_not_set(self) -> None:
        workshop = create_workshop(suffix=65)
        budget = create_budget(workshop=workshop)
        context = build_budget_pdf_context(budget=budget)
        self.assertEqual(context["observations"], "")

    def test_pdf_context_includes_fixed_observation_from_workshop(self) -> None:
        workshop = create_workshop(suffix=66)
        workshop.pdf_observation = "Observação fixa da oficina."
        workshop.save(update_fields=["pdf_observation"])
        budget = create_budget(workshop=workshop)
        context = build_budget_pdf_context(budget=budget)
        self.assertEqual(context["fixed_observation"], "Observação fixa da oficina.")

    def test_pdf_context_fixed_observation_empty_when_workshop_has_none(self) -> None:
        workshop = create_workshop(suffix=67)
        budget = create_budget(workshop=workshop)
        context = build_budget_pdf_context(budget=budget)
        self.assertEqual(context["fixed_observation"], "")
