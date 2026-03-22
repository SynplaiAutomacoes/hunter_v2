from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlparse
from unittest.mock import PropertyMock, patch

import requests
from django.http import QueryDict
from django.template import Context, Template
from apps.accounts.models import Account, User
from django.http import Http404, HttpResponse
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.budget.forms.shared import _render_budget_items_rows
from apps.budget.models import Budget, BudgetItem, BudgetStatus, SignatureStatus
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
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.kits import Kit, KitProduct, KitService
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.documents.contract import DocumentPayload, SignatureDeliveryResult
from apps.core.documents.signature import normalize_signature_phone_number, parse_document_signature_token
from apps.core.documents.services import SignatureDeliveryServiceError, get_signed_document_url
from apps.workorder.models import WorkOrder
from apps.budget.views.pdf_views import signature_file, signature_preview, visualizar_pdf_assinatura
from apps.budget.views.workflow_views import BUDGET_LIST_FILTERS, trigger_signature_send_if_needed
from apps.collaborators.models import WorkshopCollaborator
from apps.core.query_filters import apply_query_param_filters
from apps.customer.models import Customer, Vehicle
from apps.collaborators.models import WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.workshops import Workshop


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

    budget = Budget(workshop=workshop, entry_date=timezone.now().date())
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


def create_vehicle(*, workshop: Workshop, customer: Customer, suffix: int = 1, plate: str | None = None) -> Vehicle:
    return Vehicle.objects.create(
        workshop=workshop,
        customer=customer,
        plate=plate or f"ABC1D{suffix:02d}",
        brand=f"Marca {suffix}",
        model=f"Modelo {suffix}",
        year_fabrication="2024",
        year_model="2024",
        color="Prata",
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


def create_product(*, workshop: Workshop, suffix: int = 1, application: str = "") -> Product:
    group = CatalogGroup.objects.create(workshop=workshop, name=f"Grupo {suffix}")
    return Product.objects.create(
        workshop=workshop,
        code=f"P-{suffix:03d}",
        unit=Product.Unit.UND,
        name=f"Produto {suffix}",
        description=f"Descricao {suffix}",
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


def create_kit(*, workshop: Workshop, suffix: int, products: list[tuple[Product, int]]) -> Kit:
    kit = Kit.objects.create(workshop=workshop, name=f"Kit {suffix}")
    for product, quantity in products:
        KitProduct.objects.create(kit=kit, product=product, quantity=quantity)
    return kit


def extract_token_from_url(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1]


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

        other_customer = create_customer(workshop=workshop, suffix=71)
        other_vehicle = create_vehicle(workshop=workshop, customer=other_customer, suffix=71, plate="XYZ9876")
        other_collaborator = create_collaborator(workshop=workshop, suffix=71, name="Maria Souza")
        other_budget = create_budget(workshop=workshop)
        other_budget.customer = other_customer
        other_budget.vehicle = other_vehicle
        other_budget.collaborator = other_collaborator
        other_budget.status = BudgetStatus.CANCELLED
        other_budget.save(update_fields=["customer", "vehicle", "collaborator", "status"])

        params = QueryDict("client=Cliente+70&vehicle=ABC1234&collaborator=Joao&status=approved")

        filtered = apply_query_param_filters(
            Budget.objects.filter(workshop=workshop),
            params=params,
            filter_configs=BUDGET_LIST_FILTERS,
        )

        self.assertQuerySetEqual(filtered.order_by("pk"), [matching_budget], transform=lambda obj: obj)
        self.assertNotIn(other_budget, filtered)

    def test_budget_filter_fields_template_renders_new_inputs(self) -> None:
        request = RequestFactory().get("/budget/", {"client": "Ana", "vehicle": "ABC1234", "collaborator": "Joao", "status": BudgetStatus.APPROVED})
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
        self.assertIn('value="Ana"', html)
        self.assertIn('value="ABC1234"', html)
        self.assertIn('value="Joao"', html)


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

        with patch.object(Budget, "calculate_pricing_methods", side_effect=AssertionError("Nao deve usar metodo de precificacao para total_base_value")):
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


class BudgetSignaturePublicViewTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @patch("apps.budget.views.pdf_views.render")
    @patch("apps.budget.views.pdf_views.build_budget_pdf_context")
    def test_signature_preview_renders_budget_pdf_template(self, build_context_mock, render_mock) -> None:
        workshop = create_workshop(suffix=78)
        budget = create_budget(workshop=workshop)
        token = extract_token_from_url(build_signature_preview_url(budget=budget))

        build_context_mock.return_value = {"budget": budget, "observacao": workshop.pdf_observation}
        render_mock.return_value = HttpResponse("preview")

        response = signature_preview(self.factory.get("/"), token)

        self.assertEqual(response.content, b"preview")
        render_mock.assert_called_once()
        self.assertEqual(render_mock.call_args.args[1], "budget/partials/pdf/visualizarPDF.html")
        self.assertEqual(render_mock.call_args.args[2], {"budget": budget, "observacao": workshop.pdf_observation})

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
