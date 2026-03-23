from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlparse
from unittest.mock import patch

from apps.accounts.models import Account, User
from django.db import connection
from django.http import Http404, HttpResponse, QueryDict
from django.template import Context, Template
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.budget.documents.provider import build_budget_pdf_render_request
from apps.budget.models import Budget, BudgetItem
from apps.catalog.models.kits import Kit, KitProduct, KitService
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.collaborators.models import WorkshopMember
from apps.core.documents.contract import DocumentPayload, SignatureDeliveryResult
from apps.core.documents.services import SignatureDeliveryServiceError
from apps.core.documents.signature import normalize_signature_phone_number, parse_document_signature_token
from apps.core.query_filters import apply_query_param_filters
from apps.customer.models import Customer, Vehicle
from apps.finance.models.payment_method import PaymentMethod
from apps.iam.utils import get_or_create_director_role
from apps.stock.models import StockMovement, StockProduct
from apps.workorder.forms import WorkOrderPaymentForm
from apps.workorder.approval import approve_workorder_with_stock
from apps.workorder.documents.provider import build_workorder_pdf_render_request
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderPaymentMethod, WorkOrderSignatureStatus, WorkOrderStatus
from apps.workorder.service import (
    WORKORDER_SIGNATURE_DOCUMENT_ID_KEY,
    WORKORDER_SIGNATURE_TOKEN_SALT,
    build_signature_file_url,
    build_signature_payload,
    build_signature_preview_url,
    send_workorder_for_signature,
)
from apps.workorder.views import WORKORDER_LIST_FILTERS, signature_file, signature_preview, visualizar_pdf_workorder
from apps.workshops.models.workshops import Workshop


WORKORDER_TEST_DEFAULTS_PREPARED = False


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina OS {suffix}",
        cnpj=f"11.333.444/0001-{suffix:02d}",
        phone="+5511988888888",
        address="Rua Teste OS, 123",
    )


def create_director_user_with_workshop(*, suffix: int = 1) -> tuple[User, Workshop]:
    user = User.objects.create_user(username=f"workorder-director{suffix}", password="123", cpf=f"98765432{suffix:03d}")
    account = Account.objects.create(name=f"Conta OS {suffix}", owner=user)
    user.account = account
    user.is_account_owner = True
    user.save(update_fields=["account", "is_account_owner"])

    workshop = Workshop.objects.create(
        account=account,
        name=f"Oficina Diretor OS {suffix}",
        cnpj=f"11.444.555/0001-{suffix:02d}",
        phone="+5511977777777",
        address="Rua Diretor OS, 123",
    )

    director_role = get_or_create_director_role(account=account, with_all_permissions=True)
    WorkshopMember.objects.create(user=user, workshop=workshop, role=director_role, is_active=True)
    return user, workshop


def create_budget(*, workshop: Workshop) -> Budget:
    global WORKORDER_TEST_DEFAULTS_PREPARED

    if not WORKORDER_TEST_DEFAULTS_PREPARED:
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE budget_budget ALTER COLUMN discount_percentage SET DEFAULT 0")
        WORKORDER_TEST_DEFAULTS_PREPARED = True

    budget = Budget(workshop=workshop, entry_date=timezone.now().date())
    budget.save()
    return budget


def create_customer(*, workshop: Workshop, suffix: int = 1, phone: str = "+5511988888888") -> Customer:
    return Customer.objects.create(
        workshop=workshop,
        name=f"Cliente OS {suffix}",
        cpf_or_cnpj=f"987.654.321-{suffix:02d}",
        email=f"cliente.os{suffix}@example.com",
        phone=phone,
    )


def create_vehicle(*, workshop: Workshop, customer: Customer, suffix: int = 1, plate: str | None = None) -> Vehicle:
    return Vehicle.objects.create(
        workshop=workshop,
        customer=customer,
        plate=plate or f"OSP123{suffix}",
        brand=f"Marca OS {suffix}",
        model=f"Modelo OS {suffix}",
        year_fabrication="2024",
        year_model="2024",
        color="Branco",
    )


def extract_token_from_url(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1]


def create_service(*, workshop: Workshop, suffix: int = 1) -> Service:
    return Service.objects.create(
        workshop=workshop,
        name=f"Servico Teste {suffix}",
        duration=timedelta(hours=1),
        suggested_cost=Money("5.00", "BRL"),
        selling_price=Money("20.00", "BRL"),
    )


class WorkOrderListFiltersTests(TestCase):
    def test_workorder_list_filters_support_client_vehicle_and_status(self) -> None:
        workshop = create_workshop(suffix=70)

        matching_customer = create_customer(workshop=workshop, suffix=70)
        matching_vehicle = create_vehicle(workshop=workshop, customer=matching_customer, suffix=70, plate="OSA1234")
        matching_budget = create_budget(workshop=workshop)
        matching_budget.customer = matching_customer
        matching_budget.vehicle = matching_vehicle
        matching_budget.save(update_fields=["customer", "vehicle"])
        matching_workorder = WorkOrder.objects.create(workshop=workshop, budget=matching_budget, status=WorkOrderStatus.APPROVED)

        other_customer = create_customer(workshop=workshop, suffix=71)
        other_vehicle = create_vehicle(workshop=workshop, customer=other_customer, suffix=71, plate="OSB9876")
        other_budget = create_budget(workshop=workshop)
        other_budget.customer = other_customer
        other_budget.vehicle = other_vehicle
        other_budget.save(update_fields=["customer", "vehicle"])
        other_workorder = WorkOrder.objects.create(workshop=workshop, budget=other_budget, status=WorkOrderStatus.CANCELLED)

        params = QueryDict("client=Cliente+OS+70&vehicle=OSA1234&status=approved")

        filtered = apply_query_param_filters(
            WorkOrder.objects.filter(workshop=workshop),
            params=params,
            filter_configs=WORKORDER_LIST_FILTERS,
        )

        self.assertQuerySetEqual(filtered.order_by("pk"), [matching_workorder], transform=lambda obj: obj)
        self.assertNotIn(other_workorder, filtered)

    def test_workorder_filter_fields_template_renders_new_inputs(self) -> None:
        request = RequestFactory().get("/workorder/", {"client": "Ana", "vehicle": "OSA1234", "status": WorkOrderStatus.APPROVED})
        template = Template("{% include 'workorder/partials/workorder_filters_fields.html' %}")

        html = template.render(
            Context(
                {
                    "request": request,
                    "table_id": "workorder-table",
                    "status_choices": WorkOrderStatus.choices,
                }
            )
        )

        self.assertIn('name="client"', html)
        self.assertIn('name="vehicle"', html)
        self.assertIn('name="status"', html)
        self.assertIn('value="Ana"', html)
        self.assertIn('value="OSA1234"', html)

    def _login_with_active_workshop(self, *, suffix: int) -> Workshop:
        user, workshop = create_director_user_with_workshop(suffix=suffix)
        self.client.force_login(user)

        session = self.client.session
        session["active_workshop_id"] = workshop.pk
        session.save()
        return workshop

    def test_workorder_list_hides_cancelled_by_default(self) -> None:
        workshop = self._login_with_active_workshop(suffix=72)
        approved_workorder = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)
        cancelled_workorder = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.CANCELLED)

        response = self.client.get(reverse("workorder:workorder_list"))

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["workorder"].order_by("pk"), [approved_workorder], transform=lambda obj: obj)
        self.assertNotIn(cancelled_workorder, response.context["workorder"])

    def test_workorder_list_shows_cancelled_when_cancelled_filter_is_selected(self) -> None:
        workshop = self._login_with_active_workshop(suffix=73)
        approved_workorder = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)
        cancelled_workorder = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.CANCELLED)

        response = self.client.get(reverse("workorder:workorder_list"), {"status": WorkOrderStatus.CANCELLED})

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["workorder"].order_by("pk"), [cancelled_workorder], transform=lambda obj: obj)
        self.assertNotIn(approved_workorder, response.context["workorder"])

    def test_workorder_list_keeps_cancelled_hidden_for_invalid_status_filter(self) -> None:
        workshop = self._login_with_active_workshop(suffix=74)
        approved_workorder = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)
        cancelled_workorder = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.CANCELLED)

        response = self.client.get(reverse("workorder:workorder_list"), {"status": "invalid-status"})

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["workorder"].order_by("pk"), [approved_workorder], transform=lambda obj: obj)
        self.assertNotIn(cancelled_workorder, response.context["workorder"])

    def test_workorder_list_shows_status_report_for_selected_status(self) -> None:
        workshop = self._login_with_active_workshop(suffix=75)
        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)
        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)
        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.DRAFT)

        response = self.client.get(reverse("workorder:workorder_list"), {"status": WorkOrderStatus.APPROVED})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_status_report"], {"value": WorkOrderStatus.APPROVED, "label": "Aprovado", "count": 2, "badge_class": "badge-success min-w-sm"})
        self.assertContains(response, "Relatorio do status")
        self.assertContains(response, "Aprovado")
        self.assertContains(response, "O.S. com este status")
        self.assertContains(response, "Imprimir relatorio em PDF")
        self.assertContains(response, f"url: '{reverse('workorder:status_report_pdf_preview')}?status={WorkOrderStatus.APPROVED}'")
        self.assertContains(response, f"downloadUrl: '{reverse('workorder:status_report_pdf')}?download=1&status={WorkOrderStatus.APPROVED}'")

    def test_workorder_status_report_counts_only_selected_status(self) -> None:
        workshop = self._login_with_active_workshop(suffix=76)

        matching_customer = create_customer(workshop=workshop, suffix=76)
        matching_vehicle = create_vehicle(workshop=workshop, customer=matching_customer, suffix=76, plate="OSC1234")
        matching_budget = create_budget(workshop=workshop)
        matching_budget.customer = matching_customer
        matching_budget.vehicle = matching_vehicle
        matching_budget.save(update_fields=["customer", "vehicle"])

        other_customer = create_customer(workshop=workshop, suffix=77)
        other_vehicle = create_vehicle(workshop=workshop, customer=other_customer, suffix=77, plate="OSD1234")
        other_budget = create_budget(workshop=workshop)
        other_budget.customer = other_customer
        other_budget.vehicle = other_vehicle
        other_budget.save(update_fields=["customer", "vehicle"])

        matching_workorder = WorkOrder.objects.create(workshop=workshop, budget=matching_budget, status=WorkOrderStatus.APPROVED)
        other_workorder = WorkOrder.objects.create(workshop=workshop, budget=other_budget, status=WorkOrderStatus.APPROVED)
        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.DRAFT)

        response = self.client.get(reverse("workorder:workorder_list"), {"status": WorkOrderStatus.APPROVED, "client": matching_customer.name})

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["workorder"].order_by("pk"), [matching_workorder], transform=lambda obj: obj)
        self.assertNotIn(other_workorder, response.context["workorder"])
        self.assertEqual(response.context["selected_status_report"]["count"], 2)

    def test_workorder_list_hides_status_report_without_valid_status(self) -> None:
        workshop = self._login_with_active_workshop(suffix=78)
        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)

        response = self.client.get(reverse("workorder:workorder_list"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["selected_status_report"])
        self.assertNotContains(response, "Relatorio do status")
        self.assertNotContains(response, "Imprimir relatorio em PDF")

    def test_workorder_list_htmx_partial_keeps_status_report_in_table_content(self) -> None:
        workshop = self._login_with_active_workshop(suffix=79)
        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)
        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)

        response = self.client.get(reverse("workorder:workorder_list"), {"status": WorkOrderStatus.APPROVED}, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="workorder-table-content"')
        self.assertContains(response, "Relatorio do status")
        self.assertContains(response, "Aprovado")
        self.assertContains(response, "Imprimir relatorio em PDF")


class WorkOrderStatusReportPdfTests(TestCase):
    def _login_with_active_workshop(self, *, suffix: int) -> Workshop:
        user, workshop = create_director_user_with_workshop(suffix=suffix)
        self.client.force_login(user)

        session = self.client.session
        session["active_workshop_id"] = workshop.pk
        session.save()
        return workshop

    def test_status_report_pdf_preview_renders_html_for_iframe(self) -> None:
        workshop = self._login_with_active_workshop(suffix=91)

        customer = create_customer(workshop=workshop, suffix=91)
        vehicle = create_vehicle(workshop=workshop, customer=customer, suffix=91, plate="OSP9191")
        budget = create_budget(workshop=workshop)
        budget.customer = customer
        budget.vehicle = vehicle
        budget.save(update_fields=["customer", "vehicle"])

        approved_workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.DRAFT)

        response = self.client.get(reverse("workorder:status_report_pdf_preview"), {"status": WorkOrderStatus.APPROVED})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<!DOCTYPE html>", html=False)
        self.assertContains(response, "Relat&oacute;rio de Ordens de Servi&ccedil;o por Status", html=False)
        self.assertContains(response, workshop.name)
        self.assertContains(response, "Aprovado")
        self.assertContains(response, f"#{approved_workorder.pk}")
        self.assertContains(response, customer.name)
        self.assertContains(response, vehicle.plate)
        self.assertIsNone(response.headers.get("X-Frame-Options"))

    @patch("apps.workorder.views.render_workorder_status_report_pdf_document")
    def test_status_report_pdf_view_returns_attachment_and_ignores_other_filters(self, render_document_mock) -> None:
        workshop = self._login_with_active_workshop(suffix=92)

        matching_customer = create_customer(workshop=workshop, suffix=92)
        matching_vehicle = create_vehicle(workshop=workshop, customer=matching_customer, suffix=92, plate="OSP9292")
        matching_budget = create_budget(workshop=workshop)
        matching_budget.customer = matching_customer
        matching_budget.vehicle = matching_vehicle
        matching_budget.save(update_fields=["customer", "vehicle"])

        other_customer = create_customer(workshop=workshop, suffix=93)
        other_vehicle = create_vehicle(workshop=workshop, customer=other_customer, suffix=93, plate="OSP9393")
        other_budget = create_budget(workshop=workshop)
        other_budget.customer = other_customer
        other_budget.vehicle = other_vehicle
        other_budget.save(update_fields=["customer", "vehicle"])

        matching_workorder = WorkOrder.objects.create(workshop=workshop, budget=matching_budget, status=WorkOrderStatus.APPROVED)
        other_workorder = WorkOrder.objects.create(workshop=workshop, budget=other_budget, status=WorkOrderStatus.APPROVED)
        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.DRAFT)

        render_document_mock.return_value = DocumentPayload(content=b"%PDF-status-report", filename="relatorio_ordens_servico_por_status_approved.pdf")

        response = self.client.get(
            reverse("workorder:status_report_pdf"),
            {"status": WorkOrderStatus.APPROVED, "client": matching_customer.name, "download": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-status-report")
        self.assertIn('attachment; filename="relatorio_ordens_servico_por_status_approved.pdf"', response["Content-Disposition"])

        context = render_document_mock.call_args.kwargs["context"]
        self.assertEqual(context["selected_status_report"]["count"], 2)
        self.assertCountEqual(context["report_workorders"], [matching_workorder, other_workorder])
        self.assertEqual(context["status_report_pdf_title"], "Relatorio de Ordens de Servico por Status")

    def test_status_report_pdf_views_return_404_without_valid_status(self) -> None:
        workshop = self._login_with_active_workshop(suffix=94)
        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)

        preview_response = self.client.get(reverse("workorder:status_report_pdf_preview"))
        pdf_response = self.client.get(reverse("workorder:status_report_pdf"), {"status": "invalid-status"})

        self.assertEqual(preview_response.status_code, 404)
        self.assertEqual(pdf_response.status_code, 404)


def create_product(*, workshop: Workshop, suffix: int = 1, selling_price: str = "100.00") -> Product:
    group = CatalogGroup.objects.create(workshop=workshop, name=f"Grupo Produto {suffix}")
    return Product.objects.create(
        workshop=workshop,
        code=f"P-{suffix:03d}",
        unit=Product.Unit.UND,
        name=f"Produto Teste {suffix}",
        group=group,
        cost_price=Money("10.00", "BRL"),
        selling_price=Money(selling_price, "BRL"),
    )


def create_kit(*, workshop: Workshop, suffix: int, products: list[tuple[Product, int]]) -> Kit:
    kit = Kit.objects.create(workshop=workshop, name=f"Kit {suffix}")
    for product, quantity in products:
        KitProduct.objects.create(kit=kit, product=product, quantity=quantity)
    return kit


class WorkOrderTotalsConsistencyTests(TestCase):
    def test_total_base_value_uses_workorder_item_selling_totals_only(self) -> None:
        workshop = create_workshop(suffix=81)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        group = CatalogGroup.objects.create(workshop=workshop, name="Grupo Teste")
        product = Product.objects.create(
            workshop=workshop,
            code="P-001",
            unit=Product.Unit.UND,
            name="Produto Teste",
            group=group,
            cost_price=Money("50.00", "BRL"),
            selling_price=Money("100.00", "BRL"),
        )
        service = Service.objects.create(
            workshop=workshop,
            name="Servico Teste",
            duration=timedelta(hours=1),
            suggested_cost=Money("0.00", "BRL"),
            selling_price=Money("0.01", "BRL"),
        )

        WorkOrderItem.objects.create(
            workshop=workshop,
            workorder=workorder,
            product=product,
            quantity=2,
            shipping=Money("5.00", "BRL"),
        )
        WorkOrderItem.objects.create(
            workshop=workshop,
            workorder=workorder,
            service=service,
            quantity=1,
        )

        with patch.object(WorkOrder, "calculate_pricing_methods", side_effect=AssertionError("Nao deve usar metodo de precificacao para total_base_value")):
            self.assertEqual(workorder.total_products_value, Money("205.00", "BRL"))
            self.assertEqual(workorder.total_services_value, Money("0.01", "BRL"))
            self.assertEqual(workorder.total_base_value, Money("205.01", "BRL"))

    def test_total_budget_value_applies_discount_over_item_totals(self) -> None:
        workshop = create_workshop(suffix=82)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        group = CatalogGroup.objects.create(workshop=workshop, name="Grupo Desconto")
        product = Product.objects.create(
            workshop=workshop,
            code="P-002",
            unit=Product.Unit.UND,
            name="Produto Desconto",
            group=group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("15.00", "BRL"),
        )
        WorkOrderItem.objects.create(
            workshop=workshop,
            workorder=workorder,
            product=product,
            quantity=1,
        )

        workorder.discount_value = Money(Decimal("5.00"), "BRL")
        workorder.save(update_fields=["discount_value"])

        self.assertEqual(workorder.total_base_value, Money("15.00", "BRL"))
        self.assertEqual(workorder.total_budget_value, Money("10.00", "BRL"))

    def test_sync_from_budget_uses_resolved_discount_value_from_percentage(self) -> None:
        workshop = create_workshop(suffix=83)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        group = CatalogGroup.objects.create(workshop=workshop, name="Grupo Percentual")
        product = Product.objects.create(
            workshop=workshop,
            code="P-003",
            unit=Product.Unit.UND,
            name="Produto Percentual",
            group=group,
            cost_price=Money("20.00", "BRL"),
            selling_price=Money("100.00", "BRL"),
        )
        BudgetItem.objects.create(
            workshop=workshop,
            budget=budget,
            product=product,
            quantity=1,
        )

        budget.discount_percentage = Decimal("0.10")
        budget.discount_value = Money("0.00", "BRL")
        budget.save(update_fields=["discount_percentage", "discount_value"])

        workorder.sync_from_budget()
        workorder.refresh_from_db()

        self.assertEqual(workorder.discount_value, Money("10.00", "BRL"))

    def test_discount_percentage_display_uses_current_totals(self) -> None:
        workshop = create_workshop(suffix=84)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        group = CatalogGroup.objects.create(workshop=workshop, name="Grupo Display")
        product = Product.objects.create(
            workshop=workshop,
            code="P-004",
            unit=Product.Unit.UND,
            name="Produto Display",
            group=group,
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("200.00", "BRL"),
        )
        WorkOrderItem.objects.create(
            workshop=workshop,
            workorder=workorder,
            product=product,
            quantity=1,
        )

        workorder.discount_value = Money("30.00", "BRL")
        workorder.save(update_fields=["discount_value"])

        self.assertEqual(workorder.discount_percentage_display, "15,00%")


class WorkOrderSignatureTokenModelTests(TestCase):
    def test_workorder_starts_with_active_signature_token(self) -> None:
        workshop = create_workshop(suffix=90)
        budget = create_budget(workshop=workshop)

        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        self.assertEqual(workorder.signature_token_version, 1)
        self.assertTrue(workorder.signature_token_active)

    def test_revoke_signature_token_disables_current_token(self) -> None:
        workshop = create_workshop(suffix=91)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        workorder.revoke_signature_token()
        workorder.refresh_from_db()

        self.assertFalse(workorder.signature_token_active)
        self.assertEqual(workorder.signature_token_version, 1)

    def test_regenerate_signature_token_increments_version_and_reactivates(self) -> None:
        workshop = create_workshop(suffix=92)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.revoke_signature_token()

        workorder.regenerate_signature_token()
        workorder.refresh_from_db()

        self.assertEqual(workorder.signature_token_version, 2)
        self.assertTrue(workorder.signature_token_active)


class WorkOrderSignaturePersistenceTests(TestCase):
    def test_mark_signature_sent_persists_envelope_and_document_id(self) -> None:
        workshop = create_workshop(suffix=86)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        workorder.mark_signature_sent("env-123", document_id="doc-123")
        workorder.refresh_from_db()

        self.assertEqual(workorder.signature_external_id, "env-123")
        self.assertEqual(workorder.signature_document_id, "doc-123")
        self.assertEqual(workorder.signature_request_status, WorkOrderSignatureStatus.SENT)
        self.assertIsNotNone(workorder.signature_sent_at)


class WorkOrderSignatureTokenUrlTests(TestCase):
    def test_build_signature_payload_uses_workorder_specific_key(self) -> None:
        workshop = create_workshop(suffix=93)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        payload = build_signature_payload(workorder)

        self.assertEqual(payload, {"workorder_id": workorder.id, "version": workorder.signature_token_version})

    @override_settings(APP_BASE_URL="https://app.example.com")
    def test_build_signature_preview_url_generates_tokenized_workorder_link(self) -> None:
        workshop = create_workshop(suffix=94)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        url = build_signature_preview_url(workorder=workorder)
        token = extract_token_from_url(url)

        payload = parse_document_signature_token(
            token=token,
            token_salt=WORKORDER_SIGNATURE_TOKEN_SALT,
            document_id_key=WORKORDER_SIGNATURE_DOCUMENT_ID_KEY,
        )

        self.assertEqual(payload.document_id, workorder.id)
        self.assertEqual(payload.version, workorder.signature_token_version)

    @override_settings(APP_BASE_URL="https://app.example.com")
    def test_build_signature_file_url_generates_tokenized_workorder_link(self) -> None:
        workshop = create_workshop(suffix=95)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        url = build_signature_file_url(workorder=workorder)
        token = extract_token_from_url(url)

        payload = parse_document_signature_token(
            token=token,
            token_salt=WORKORDER_SIGNATURE_TOKEN_SALT,
            document_id_key=WORKORDER_SIGNATURE_DOCUMENT_ID_KEY,
        )

        self.assertEqual(payload.document_id, workorder.id)
        self.assertEqual(payload.version, workorder.signature_token_version)


class WorkOrderSignaturePublicViewTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @patch("apps.workorder.views.render")
    @patch("apps.workorder.views.build_workorder_pdf_render_request")
    def test_signature_preview_renders_budget_pdf_template(self, build_render_request_mock, render_mock) -> None:
        workshop = create_workshop(suffix=96)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        token = extract_token_from_url(build_signature_preview_url(workorder=workorder))

        build_render_request_mock.return_value = build_budget_pdf_render_request(budget=budget)
        render_mock.return_value = HttpResponse("preview")

        response = signature_preview(self.factory.get("/"), token)

        self.assertEqual(response.content, b"preview")
        self.assertEqual(render_mock.call_args.args[1], "budget/partials/pdf/visualizarPDF.html")
        self.assertEqual(render_mock.call_args.args[2]["budget"], budget)


class WorkOrderPdfParityTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_build_workorder_pdf_render_request_reuses_budget_render_request_shape(self) -> None:
        workshop = create_workshop(suffix=99)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        filename = "documento.pdf"

        workorder_render_request = build_workorder_pdf_render_request(workorder=workorder, filename=filename)
        budget_render_request = build_budget_pdf_render_request(budget=budget, filename=filename)

        self.assertEqual(workorder_render_request.template_name, budget_render_request.template_name)
        self.assertEqual(workorder_render_request.filename, budget_render_request.filename)
        self.assertEqual(workorder_render_request.context["budget"], budget)
        self.assertEqual(workorder_render_request.context["pages"], budget_render_request.context["pages"])

    def test_build_workorder_pdf_render_request_uses_workorder_filename_by_default(self) -> None:
        workshop = create_workshop(suffix=89)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        render_request = build_workorder_pdf_render_request(workorder=workorder)

        self.assertEqual(render_request.filename, f"ordem_servico_{workorder.id}.pdf")


class WorkOrderInternalPdfTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @patch("apps.workorder.views.get_active_workshop_or_404")
    @patch("apps.workorder.views.download_signed_document_content")
    def test_visualizar_pdf_workorder_returns_signed_pdf_when_available(self, download_signed_mock, active_workshop_mock) -> None:
        workshop = create_workshop(suffix=87)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.signature_request_status = WorkOrderSignatureStatus.APPROVED
        workorder.signature_external_id = "env-87"
        workorder.signature_document_id = "doc-87"
        workorder.save(update_fields=["signature_request_status", "signature_external_id", "signature_document_id"])

        active_workshop_mock.return_value = workshop
        download_signed_mock.return_value = b"%PDF-signed"

        request = self.factory.get("/", {"download": "1"})
        response = visualizar_pdf_workorder(request, workorder.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-signed")
        self.assertIn("attachment;", response["Content-Disposition"])
        download_signed_mock.assert_called_once_with(document_id="doc-87", envelope_id="env-87")

    @patch("apps.workorder.views.get_active_workshop_or_404")
    @patch("apps.workorder.views.render_workorder_pdf_document")
    @patch("apps.workorder.views.download_signed_document_content")
    def test_visualizar_pdf_workorder_falls_back_to_base_pdf(self, download_signed_mock, render_document_mock, active_workshop_mock) -> None:
        workshop = create_workshop(suffix=88)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.signature_request_status = WorkOrderSignatureStatus.APPROVED
        workorder.signature_external_id = "env-88"
        workorder.save(update_fields=["signature_request_status", "signature_external_id"])

        active_workshop_mock.return_value = workshop
        download_signed_mock.side_effect = SignatureDeliveryServiceError("erro")
        render_document_mock.return_value = DocumentPayload(
            content=b"%PDF-base",
            filename=f"ordem_servico_{workorder.id}_base.pdf",
        )

        response = visualizar_pdf_workorder(self.factory.get("/"), workorder.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-base")
        self.assertIn('inline; filename="ordem_servico_', response["Content-Disposition"])
        download_signed_mock.assert_called_once_with(document_id=None, envelope_id="env-88")

    def test_signature_preview_rejects_inactive_token(self) -> None:
        workshop = create_workshop(suffix=97)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.revoke_signature_token()
        token = extract_token_from_url(build_signature_preview_url(workorder=workorder))

        with self.assertRaises(Http404):
            signature_preview(self.factory.get("/"), token)

    @patch("apps.workorder.views.render_workorder_pdf_document")
    def test_signature_file_returns_inline_pdf(self, render_document_mock) -> None:
        workshop = create_workshop(suffix=98)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        token = extract_token_from_url(build_signature_file_url(workorder=workorder))

        render_document_mock.return_value = DocumentPayload(
            content=b"%PDF-workorder",
            filename=f"ordem_servico_{workorder.id}.pdf",
        )

        response = signature_file(self.factory.get("/"), token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-workorder")
        self.assertIn('inline; filename="ordem_servico_', response["Content-Disposition"])


class WorkOrderSignatureDeliveryTests(TestCase):
    @patch("apps.workorder.service.send_document_for_signature")
    @patch("apps.workorder.service.render_workorder_pdf_document")
    def test_send_workorder_for_signature_uses_core_payload_builders(self, render_pdf_mock, send_document_mock) -> None:
        workshop = create_workshop(suffix=83)
        budget = create_budget(workshop=workshop)
        customer = create_customer(workshop=workshop, suffix=83)
        budget.customer = customer
        budget.save(update_fields=["customer"])
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        render_pdf_mock.return_value = DocumentPayload(content=b"workorder-pdf", filename="os.pdf")
        send_document_mock.return_value = SignatureDeliveryResult(
            envelope_id="env-83",
            document_id="doc-83",
            provider="supersign",
            raw_response={"ok": True},
        )

        result = send_workorder_for_signature(workorder=workorder)

        self.assertEqual(result.envelope_id, "env-83")
        _, kwargs = send_document_mock.call_args
        self.assertEqual(kwargs["file_name"], f"ordem_servico-{workorder.id}.pdf")
        self.assertEqual(kwargs["document_ref_id"], f"workorder-{workorder.id}")
        self.assertEqual(kwargs["title"], f"Ordem de servico #{workorder.id}")
        self.assertEqual(kwargs["message"], "Segue ordem de servico para assinatura.")
        self.assertEqual(kwargs["signatory"]["id"], f"customer-{workorder.id}")
        self.assertEqual(kwargs["signatory"]["authMethod"], "WHATSAPP")
        self.assertEqual(kwargs["signatory"]["phoneNumber"], normalize_signature_phone_number(customer.phone))
        self.assertEqual(kwargs["observers"][0]["email"], customer.email)
        self.assertEqual(kwargs["fields"][0]["documentId"], f"workorder-{workorder.id}")
        self.assertEqual(kwargs["fields"][0]["signatoryId"], f"customer-{workorder.id}")
        self.assertEqual(kwargs["fields"][0]["pageNumber"], 1)


class WorkOrderDuplicateKitProductTests(TestCase):
    def test_workorder_matches_budget_slider_totals_after_duplicate_product_consolidation(self) -> None:
        workshop = create_workshop(suffix=10)
        budget = create_budget(workshop=workshop)
        product = Product.objects.create(
            workshop=workshop,
            code="P-100",
            unit=Product.Unit.UND,
            name="Coxim",
            group=CatalogGroup.objects.create(workshop=workshop, name="Grupo 100"),
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("15.00", "BRL"),
        )
        service = create_service(workshop=workshop, suffix=100)
        kit_1 = create_kit(workshop=workshop, suffix=1001, products=[(product, 2)])
        kit_2 = create_kit(workshop=workshop, suffix=1002, products=[(product, 1)])

        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_1, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_2, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, service=service, quantity=1)

        budget.slider = -50
        budget.save(update_fields=["slider"])

        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.sync_from_budget()

        self.assertEqual(workorder.total_products_value, budget.total_products_value)
        self.assertEqual(workorder.get_total_products_by_slider, budget.get_total_products_by_slider)
        self.assertEqual(workorder.get_total_services_by_slider, budget.get_total_services_by_slider)
        self.assertEqual(workorder.total_budget_value, budget.total_budget_value)
        self.assertEqual(workorder.pricing_snapshot.product_lines[0].quantity, 3)

    def test_workorder_matches_budget_after_duplicate_service_consolidation(self) -> None:
        workshop = create_workshop(suffix=12)
        budget = create_budget(workshop=workshop)
        service = create_service(workshop=workshop, suffix=120)
        kit_1 = create_kit(workshop=workshop, suffix=1201, products=[])
        kit_2 = create_kit(workshop=workshop, suffix=1202, products=[])
        KitService.objects.create(kit=kit_1, service=service, quantity=2, duration=service.duration)
        KitService.objects.create(kit=kit_2, service=service, quantity=1, duration=service.duration)

        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_1, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_2, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, service=service, quantity=1)

        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.sync_from_budget()

        self.assertEqual(workorder.total_services_value, budget.total_services_value)
        self.assertEqual(workorder.get_total_services_by_slider, budget.get_total_services_by_slider)
        self.assertEqual(workorder.pricing_snapshot.service_lines[0].quantity, 3)

    def test_stock_approval_uses_consolidated_product_quantity(self) -> None:
        workshop = create_workshop(suffix=11)
        budget = create_budget(workshop=workshop)
        product = Product.objects.create(
            workshop=workshop,
            code="P-101",
            unit=Product.Unit.UND,
            name="Coxim Estoque",
            ncm="87089990",
            group=CatalogGroup.objects.create(workshop=workshop, name="Grupo 101"),
            cost_price=Money("10.00", "BRL"),
            selling_price=Money("15.00", "BRL"),
        )
        kit_1 = create_kit(workshop=workshop, suffix=1011, products=[(product, 2)])
        kit_2 = create_kit(workshop=workshop, suffix=1012, products=[(product, 1)])

        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_1, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit_2, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=1)

        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.sync_from_budget()

        stock_product, _ = StockProduct.objects.get_or_create(
            workshop=workshop,
            product=product,
            defaults={"current_quantity": 3},
        )
        stock_product.current_quantity = 3
        stock_product.save(update_fields=["current_quantity"])

        approve_workorder_with_stock(workorder=workorder)

        stock_product.refresh_from_db()
        workorder.refresh_from_db()
        self.assertEqual(stock_product.current_quantity, 0)
        self.assertEqual(workorder.status, WorkOrderStatus.APPROVED)
        self.assertEqual(StockMovement.objects.get(stock_product=stock_product).quantity, 3)


class WorkOrderPaymentFormTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=21)
        self.budget = create_budget(workshop=self.workshop)
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget)

    def _set_workorder_total(self, value: str, *, suffix: int) -> None:
        self.workorder.items.all().delete()
        product = create_product(workshop=self.workshop, suffix=suffix, selling_price=value)
        WorkOrderItem.objects.create(workshop=self.workshop, workorder=self.workorder, product=product, quantity=1)

    def test_form_saves_entered_amount_as_payment_total(self) -> None:
        self._set_workorder_total("100.00", suffix=21)
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Cartão", installments_count=4)

        form = WorkOrderPaymentForm(
            data={
                "payment_method": str(payment_method.pk),
                "first_installment_amount_0": "40.00",
                "first_installment_amount_1": "BRL",
                "due_date": "2026-03-20",
            },
            workorder=self.workorder,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["installments_count"], 4)
        self.assertEqual(form.cleaned_data["remaining_installments_amount"], Money("0.00", "BRL"))

        payment = form.save(commit=False)
        payment.workorder = self.workorder
        payment.save()

        self.assertEqual(payment.installments_count, 4)
        self.assertEqual(payment.first_installment_amount, Money("40.00", "BRL"))
        self.assertEqual(payment.remaining_installments_amount, Money("0.00", "BRL"))
        self.assertEqual(payment.total_paid, Money("40.00", "BRL"))
        self.assertEqual(payment.due_date, date(2026, 3, 20))

    def test_form_allows_paying_full_pending_amount(self) -> None:
        self._set_workorder_total("100.00", suffix=22)
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Cartão Premium", installments_count=4)

        form = WorkOrderPaymentForm(
            data={
                "payment_method": str(payment_method.pk),
                "first_installment_amount_0": "100.00",
                "first_installment_amount_1": "BRL",
                "due_date": "2026-03-21",
            },
            workorder=self.workorder,
        )

        self.assertTrue(form.is_valid(), form.errors)
        payment = form.save(commit=False)
        payment.workorder = self.workorder
        payment.save()

        self.assertEqual(payment.total_paid, Money("100.00", "BRL"))

    def test_form_defaults_due_date_to_today_when_not_provided(self) -> None:
        self._set_workorder_total("100.00", suffix=23)
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix", installments_count=1)

        form = WorkOrderPaymentForm(
            data={
                "payment_method": str(payment_method.pk),
                "first_installment_amount_0": "50.00",
                "first_installment_amount_1": "BRL",
                "due_date": "",
            },
            workorder=self.workorder,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["due_date"], timezone.localdate())

    def test_form_rejects_first_installment_above_pending_balance(self) -> None:
        self._set_workorder_total("100.00", suffix=24)
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Cartão Especial", installments_count=4)

        form = WorkOrderPaymentForm(
            data={
                "payment_method": str(payment_method.pk),
                "first_installment_amount_0": "100.01",
                "first_installment_amount_1": "BRL",
                "due_date": "2026-03-22",
            },
            workorder=self.workorder,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("O valor a ser pago não pode exceder o saldo pendente", str(form.errors["first_installment_amount"][0]))


class AddPaymentMethodViewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=24)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.budget = create_budget(workshop=self.workshop)
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget)
        product = create_product(workshop=self.workshop, suffix=24, selling_price="100.00")
        WorkOrderItem.objects.create(workshop=self.workshop, workorder=self.workorder, product=product, quantity=1)

    def test_post_saves_payment_and_renders_updated_list(self) -> None:
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Cartão Master/Visa", installments_count=4)

        response = self.client.post(
            reverse("workorder:add_payment", args=[self.workorder.pk]),
            data={
                "payment_method": str(payment_method.pk),
                "first_installment_amount_0": "40.00",
                "first_installment_amount_1": "BRL",
                "due_date": "2026-03-24",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cartão Master/Visa")
        self.assertContains(response, "24/03/2026")

        payment = WorkOrderPaymentMethod.objects.get(workorder=self.workorder)
        self.assertEqual(payment.installments_count, 4)
        self.assertEqual(payment.remaining_installments_amount, Money("0.00", "BRL"))
        self.assertEqual(payment.total_paid, Money("40.00", "BRL"))
        self.assertEqual(payment.due_date, date(2026, 3, 24))

    def test_update_discount_syncs_budget_and_rerenders_payment_section(self) -> None:
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=self.workorder.items.first().product,
            quantity=1,
        )

        response = self.client.post(
            reverse("workorder:update_discount", args=[self.workorder.pk]),
            data={"discount_percentage": "0.10", "discount_value_0": "0.00"},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()
        self.budget.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Condição comercial da O.S.")
        self.assertEqual(self.workorder.discount_value, Money("10.00", "BRL"))
        self.assertEqual(self.budget.discount_value, Money("10.00", "BRL"))
        self.assertEqual(self.budget.discount_percentage, Decimal("0.100000"))

    def test_payment_form_uses_pending_balance_after_discount(self) -> None:
        self.workorder.discount_value = Money("10.00", "BRL")
        self.workorder.save(update_fields=["discount_value"])

        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix", installments_count=1)
        form = WorkOrderPaymentForm(
            data={
                "payment_method": str(payment_method.pk),
                "first_installment_amount_0": "95.00",
                "first_installment_amount_1": "BRL",
                "due_date": "2026-03-24",
                "discount_value_0": "10.00",
                "discount_value_1": "BRL",
                "discount_percentage": "0.10",
            },
            workorder=self.workorder,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("saldo pendente da O.S.", str(form.errors["first_installment_amount"][0]))
