from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlparse
from unittest.mock import PropertyMock, patch

from django.contrib.auth.models import Permission
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
from apps.catalog.models.kits import Kit, KitApplication, KitProduct, KitService
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.collaborators.models import WorkshopMember
from apps.core.domain.contracts.documents import DocumentPayload, SignatureDeliveryResult
from apps.core.infrastructure.services.signature import SignatureDeliveryServiceError
from apps.core.domain.contracts.documents import normalize_signature_phone_number
from apps.core.infrastructure.services.signature import parse_document_signature_token
from apps.core.infrastructure.query_filters import apply_query_param_filters
from apps.customer.models import Customer, Vehicle
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.iam.models import WorkshopRole
from apps.iam.utils import get_or_create_director_role
from apps.stock.models import StockMovement, StockProduct
from apps.workorder.forms import WorkOrderCustomerApprovalForm, WorkOrderPaymentForm, WorkOrderStatusReasonForm
from apps.workorder.approval import WorkOrderApprovalError, approve_workorder_with_stock
from apps.workorder.documents.provider import build_workorder_pdf_render_request
from apps.workorder.models import WorkOrder, WorkOrderHistory, WorkOrderItem, WorkOrderPaymentMethod, WorkOrderSignatureStatus, WorkOrderStatus
from apps.workorder.service import (
    WORKORDER_SIGNATURE_DOCUMENT_ID_KEY,
    WORKORDER_SIGNATURE_TOKEN_SALT,
    build_signature_file_url,
    build_signature_payload,
    build_signature_preview_url,
    send_workorder_for_signature,
)
from apps.workorder.util import trigger_workorder_signature_send_if_needed
from apps.workorder.views import WORKORDER_LIST_FILTERS, signature_file, signature_preview, visualizar_pdf_workorder
from apps.workshops.models.workshops import Workshop
from apps.workshops.tests import create_manager_user_with_workshop


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
        plate=plate or f"OSP123{suffix}",
        brand=brand or f"Marca OS {suffix}",
        model=model or f"Modelo OS {suffix}",
        year_fabrication=year_fabrication,
        year_model=year_model,
        color="Branco",
        engine=engine,
        fuel=fuel,
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
        matching_created_at = (timezone.now() - timedelta(days=3)).replace(hour=12, minute=0, second=0, microsecond=0)
        WorkOrder.objects.filter(pk=matching_workorder.pk).update(criado_em=matching_created_at)

        other_customer = create_customer(workshop=workshop, suffix=71)
        other_vehicle = create_vehicle(workshop=workshop, customer=other_customer, suffix=71, plate="OSB9876")
        other_budget = create_budget(workshop=workshop)
        other_budget.customer = other_customer
        other_budget.vehicle = other_vehicle
        other_budget.save(update_fields=["customer", "vehicle"])
        other_workorder = WorkOrder.objects.create(workshop=workshop, budget=other_budget, status=WorkOrderStatus.CANCELLED)
        WorkOrder.objects.filter(pk=other_workorder.pk).update(criado_em=timezone.now() - timedelta(days=12))

        selected_date = matching_created_at.date().isoformat()
        params = QueryDict(f"client=Cliente+OS+70&vehicle=OSA1234&status=approved&data_inicial={selected_date}&data_final={selected_date}")

        filtered = apply_query_param_filters(
            WorkOrder.objects.filter(workshop=workshop),
            params=params,
            filter_configs=WORKORDER_LIST_FILTERS,
        )

        self.assertQuerySetEqual(filtered.order_by("pk"), [matching_workorder], transform=lambda obj: obj)
        self.assertNotIn(other_workorder, filtered)

    def test_workorder_filter_fields_template_renders_new_inputs(self) -> None:
        request = RequestFactory().get(
            "/workorder/",
            {"client": "Ana", "vehicle": "OSA1234", "status": WorkOrderStatus.APPROVED, "data_inicial": "2026-03-01", "data_final": "2026-03-31"},
        )
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
        self.assertIn('name="data_inicial"', html)
        self.assertIn('name="data_final"', html)
        self.assertIn('value="Ana"', html)
        self.assertIn('value="OSA1234"', html)
        self.assertIn('value="2026-03-01"', html)
        self.assertIn('value="2026-03-31"', html)

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

    def test_workorder_list_recovers_missing_active_workshop_from_user_membership(self) -> None:
        user, workshop = create_director_user_with_workshop(suffix=81)
        self.client.force_login(user)

        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)

        session = self.client.session
        session.pop("active_workshop_id", None)
        session.save()

        response = self.client.get(reverse("workorder:workorder_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.get("active_workshop_id"), workshop.pk)

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
        in_range_workorder = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)
        matching_created_at = (timezone.now() - timedelta(days=2)).replace(hour=12, minute=0, second=0, microsecond=0)
        WorkOrder.objects.filter(pk=in_range_workorder.pk).update(criado_em=matching_created_at)
        out_of_range_workorder = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)
        WorkOrder.objects.filter(pk=out_of_range_workorder.pk).update(criado_em=timezone.now() - timedelta(days=10))
        draft_workorder = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.DRAFT)
        WorkOrder.objects.filter(pk=draft_workorder.pk).update(criado_em=matching_created_at)

        selected_date = matching_created_at.date().isoformat()

        response = self.client.get(reverse("workorder:workorder_list"), {"status": WorkOrderStatus.APPROVED, "data_inicial": selected_date, "data_final": selected_date})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selection_report"]["count"], 1)
        self.assertContains(response, "Resumo da selecao")
        self.assertContains(response, "Veículo Entregue")
        self.assertContains(response, "Valor total")
        self.assertContains(response, "Imprimir selecao em PDF")
        self.assertContains(response, f"url: '{reverse('workorder:status_report_pdf_preview')}?status={WorkOrderStatus.APPROVED}")
        self.assertContains(response, f"downloadUrl: '{reverse('workorder:status_report_pdf')}?download=1&status={WorkOrderStatus.APPROVED}")
        self.assertContains(response, f"data_inicial={selected_date}")
        self.assertContains(response, f"data_final={selected_date}")

    def test_workorder_list_supports_multiple_statuses(self) -> None:
        workshop = self._login_with_active_workshop(suffix=51)
        approved_workorder = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)
        draft_workorder = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.DRAFT)
        rejected_workorder = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.REJECTED)

        params = QueryDict(mutable=True)
        params.setlist("status", [WorkOrderStatus.APPROVED, WorkOrderStatus.DRAFT])

        response = self.client.get(reverse("workorder:workorder_list"), params)

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["workorder"].order_by("pk"), [approved_workorder, draft_workorder], transform=lambda obj: obj)
        self.assertNotIn(rejected_workorder, response.context["workorder"])
        self.assertEqual(response.context["selection_report"]["count"], 2)
        self.assertEqual(len(response.context["selection_report"]["badges"]), 2)

    def test_workorder_list_filters_rejected_by_creation_date(self) -> None:
        workshop = self._login_with_active_workshop(suffix=96)

        rejected_in_range = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.REJECTED)
        matching_created_at = (timezone.now() - timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0)
        WorkOrder.objects.filter(pk=rejected_in_range.pk).update(criado_em=matching_created_at)

        rejected_out_of_range = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.REJECTED)
        WorkOrder.objects.filter(pk=rejected_out_of_range.pk).update(criado_em=timezone.now() - timedelta(days=15))

        approved_same_day = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)
        WorkOrder.objects.filter(pk=approved_same_day.pk).update(criado_em=matching_created_at)

        selected_date = matching_created_at.date().isoformat()
        response = self.client.get(reverse("workorder:workorder_list"), {"status": WorkOrderStatus.REJECTED, "data_inicial": selected_date, "data_final": selected_date})

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["workorder"].order_by("pk"), [rejected_in_range], transform=lambda obj: obj)
        self.assertNotIn(rejected_out_of_range, response.context["workorder"])
        self.assertNotIn(approved_same_day, response.context["workorder"])

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
        matching_created_at = (timezone.now() - timedelta(days=3)).replace(hour=12, minute=0, second=0, microsecond=0)
        WorkOrder.objects.filter(pk=matching_workorder.pk).update(criado_em=matching_created_at)
        other_workorder = WorkOrder.objects.create(workshop=workshop, budget=other_budget, status=WorkOrderStatus.APPROVED)
        WorkOrder.objects.filter(pk=other_workorder.pk).update(criado_em=matching_created_at)
        out_of_range_workorder = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)
        WorkOrder.objects.filter(pk=out_of_range_workorder.pk).update(criado_em=timezone.now() - timedelta(days=12))
        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.DRAFT)

        selected_date = matching_created_at.date().isoformat()
        response = self.client.get(
            reverse("workorder:workorder_list"),
            {"status": WorkOrderStatus.APPROVED, "client": matching_customer.name, "data_inicial": selected_date, "data_final": selected_date},
        )

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["workorder"].order_by("pk"), [matching_workorder], transform=lambda obj: obj)
        self.assertNotIn(other_workorder, response.context["workorder"])
        self.assertNotIn(out_of_range_workorder, response.context["workorder"])
        self.assertEqual(response.context["selection_report"]["count"], 1)

    def test_workorder_list_hides_status_report_without_valid_status(self) -> None:
        workshop = self._login_with_active_workshop(suffix=78)
        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)

        response = self.client.get(reverse("workorder:workorder_list"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["selection_report"])
        self.assertNotContains(response, "Resumo da selecao")
        self.assertNotContains(response, "Imprimir selecao em PDF")

    def test_workorder_list_htmx_partial_keeps_status_report_in_table_content(self) -> None:
        workshop = self._login_with_active_workshop(suffix=79)
        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)
        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)

        response = self.client.get(reverse("workorder:workorder_list"), {"status": WorkOrderStatus.APPROVED}, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="workorder-table-content"')
        self.assertContains(response, "Resumo da selecao")
        self.assertContains(response, "Veículo Entregue")
        self.assertContains(response, "Imprimir selecao em PDF")


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
        matching_created_at = (timezone.now() - timedelta(days=4)).replace(hour=12, minute=0, second=0, microsecond=0)
        WorkOrder.objects.filter(pk=approved_workorder.pk).update(criado_em=matching_created_at)

        other_customer = create_customer(workshop=workshop, suffix=911)
        other_vehicle = create_vehicle(workshop=workshop, customer=other_customer, suffix=911, plate="OSP9111")
        other_budget = create_budget(workshop=workshop)
        other_budget.customer = other_customer
        other_budget.vehicle = other_vehicle
        other_budget.save(update_fields=["customer", "vehicle"])
        out_of_range_workorder = WorkOrder.objects.create(workshop=workshop, budget=other_budget, status=WorkOrderStatus.APPROVED)
        WorkOrder.objects.filter(pk=out_of_range_workorder.pk).update(criado_em=timezone.now() - timedelta(days=12))
        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.DRAFT)

        selected_date = matching_created_at.date().isoformat()

        response = self.client.get(reverse("workorder:status_report_pdf_preview"), {"status": WorkOrderStatus.APPROVED, "data_inicial": selected_date, "data_final": selected_date})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<!DOCTYPE html>", html=False)
        self.assertContains(response, "Relatorio de Ordens de Servico Filtradas")
        self.assertContains(response, workshop.name)
        self.assertContains(response, "Veículo Entregue")
        self.assertContains(response, str(approved_workorder.pk))
        self.assertContains(response, customer.name)
        self.assertContains(response, vehicle.plate)
        self.assertNotContains(response, f"#{out_of_range_workorder.pk}")
        self.assertContains(response, matching_created_at.strftime("%d/%m/%Y"))
        self.assertIsNone(response.headers.get("X-Frame-Options"))

    @patch("apps.workorder.views.build_workshop_logo_data_uri", return_value="data:image/png;base64,bW9uZ28tbG9nbw==")
    def test_status_report_pdf_preview_includes_workshop_logo_data_uri(self, build_workshop_logo_data_uri_mock) -> None:
        workshop = self._login_with_active_workshop(suffix=95)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)

        response = self.client.get(reverse("workorder:status_report_pdf_preview"), {"status": WorkOrderStatus.APPROVED})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'src="data:image/png;base64,bW9uZ28tbG9nbw=="', html=False)
        build_workshop_logo_data_uri_mock.assert_called_once_with(workshop=workshop)
        self.assertContains(response, f"#{workorder.pk}")

    @patch("apps.workorder.views.render_workorder_status_report_pdf_document")
    def test_status_report_pdf_view_returns_attachment_with_filtered_selection(self, render_document_mock) -> None:
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
        matching_created_at = (timezone.now() - timedelta(days=5)).replace(hour=12, minute=0, second=0, microsecond=0)
        WorkOrder.objects.filter(pk=matching_workorder.pk).update(criado_em=matching_created_at)
        other_workorder = WorkOrder.objects.create(workshop=workshop, budget=other_budget, status=WorkOrderStatus.APPROVED)
        WorkOrder.objects.filter(pk=other_workorder.pk).update(criado_em=matching_created_at)
        out_of_range_workorder = WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.APPROVED)
        WorkOrder.objects.filter(pk=out_of_range_workorder.pk).update(criado_em=timezone.now() - timedelta(days=16))
        WorkOrder.objects.create(workshop=workshop, budget=create_budget(workshop=workshop), status=WorkOrderStatus.DRAFT)

        render_document_mock.return_value = DocumentPayload(content=b"%PDF-status-report", filename="relatorio_ordens_servico_filtradas.pdf")
        selected_date = matching_created_at.date().isoformat()

        response = self.client.get(
            reverse("workorder:status_report_pdf"),
            {"status": WorkOrderStatus.APPROVED, "client": matching_customer.name, "data_inicial": selected_date, "data_final": selected_date, "download": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-status-report")
        self.assertIn('attachment; filename="relatorio_ordens_servico_filtradas.pdf"', response["Content-Disposition"])

        context = render_document_mock.call_args.kwargs["context"]
        self.assertEqual(context["selection_report"]["count"], 1)
        self.assertCountEqual(context["report_workorders"], [matching_workorder])
        self.assertNotIn(other_workorder, context["report_workorders"])
        self.assertNotIn(out_of_range_workorder, context["report_workorders"])
        self.assertEqual(context["status_report_pdf_title"], "Relatorio de Ordens de Servico Filtradas")
        self.assertEqual(context["status_report_period_label"], f"{matching_created_at.strftime('%d/%m/%Y')} a {matching_created_at.strftime('%d/%m/%Y')}")

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
        ncm="87089990",
        group=group,
        cost_price=Money("10.00", "BRL"),
        selling_price=Money(selling_price, "BRL"),
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


class WorkOrderItemPriceTrackingTests(TestCase):
    def test_workorder_item_updates_product_last_used_price(self) -> None:
        workshop = create_workshop(suffix=21)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        product = create_product(workshop=workshop, suffix=210, selling_price="125.00")
        product.last_used_price = None
        product.save(update_fields=["last_used_price"])

        item = WorkOrderItem.objects.create(workshop=workshop, workorder=workorder, product=product, quantity=1)

        product.refresh_from_db()
        self.assertEqual(item.product_selling_price, Money("125.00", "BRL"))
        self.assertEqual(product.last_used_price, Money("125.00", "BRL"))

    def _login_with_active_workshop(self, *, suffix: int) -> Workshop:
        user, workshop = create_director_user_with_workshop(suffix=suffix)
        self.client.force_login(user)

        session = self.client.session
        session["active_workshop_id"] = workshop.pk
        session.save()
        return workshop

    def test_edit_item_requires_confirmation_for_price_below_last_used_price(self) -> None:
        workshop = self._login_with_active_workshop(suffix=22)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        product = create_product(workshop=workshop, suffix=220, selling_price="40.00")
        product.last_used_price = Money("30.00", "BRL")
        product.save(update_fields=["last_used_price", "selling_price"])
        item = WorkOrderItem.objects.create(workshop=workshop, workorder=workorder, product=product, quantity=1)

        response = self.client.post(
            reverse("workorder:edit_item", args=[workorder.pk, item.pk]),
            {
                "description": item.description,
                "quantity": "1",
                "product_cost_price_0": "10.00",
                "product_cost_price_1": "BRL",
                "product_selling_price_0": "20.00",
                "product_selling_price_1": "BRL",
                "shipping_0": "0.00",
                "shipping_1": "BRL",
                "active_tab": "products",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Último valor usado: R$ 40,00")
        item.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(item.product_selling_price, Money("40.00", "BRL"))
        self.assertEqual(product.last_used_price, Money("40.00", "BRL"))

    def test_edit_item_allows_confirmed_price_below_last_used_price(self) -> None:
        workshop = self._login_with_active_workshop(suffix=23)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        product = create_product(workshop=workshop, suffix=230, selling_price="40.00")
        product.last_used_price = Money("30.00", "BRL")
        product.save(update_fields=["last_used_price", "selling_price"])
        item = WorkOrderItem.objects.create(workshop=workshop, workorder=workorder, product=product, quantity=1)

        response = self.client.post(
            reverse("workorder:edit_item", args=[workorder.pk, item.pk]),
            {
                "description": item.description,
                "quantity": "1",
                "product_cost_price_0": "10.00",
                "product_cost_price_1": "BRL",
                "product_selling_price_0": "20.00",
                "product_selling_price_1": "BRL",
                "shipping_0": "0.00",
                "shipping_1": "BRL",
                "active_tab": "products",
                "confirm_lower_price": "1",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Retarget"), "#modal-container")
        self.assertIn("workorderCloseItemModal", response.headers.get("HX-Trigger-After-Swap", ""))
        self.assertContains(response, 'id="resume-section" hx-swap-oob="innerHTML"', html=False)
        item.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(item.product_selling_price, Money("20.00", "BRL"))
        self.assertEqual(product.last_used_price, Money("20.00", "BRL"))

    def test_edit_item_success_response_renders_updated_modal_table_value(self) -> None:
        workshop = self._login_with_active_workshop(suffix=24)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        product = create_product(workshop=workshop, suffix=240, selling_price="40.00")
        item = WorkOrderItem.objects.create(workshop=workshop, workorder=workorder, product=product, quantity=1)

        response = self.client.post(
            reverse("workorder:edit_item", args=[workorder.pk, item.pk]),
            {
                "description": item.description,
                "quantity": "1",
                "product_cost_price_0": "10.00",
                "product_cost_price_1": "BRL",
                "product_selling_price_0": "55.00",
                "product_selling_price_1": "BRL",
                "shipping_0": "0.00",
                "shipping_1": "BRL",
                "active_tab": "products",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "55,00")
        self.assertContains(response, 'id="resume-section" hx-swap-oob="innerHTML"', html=False)


class WorkOrderDetailViewTests(TestCase):
    def _login_with_active_workshop(self, *, suffix: int) -> Workshop:
        user, workshop = create_director_user_with_workshop(suffix=suffix)
        self.client.force_login(user)

        session = self.client.session
        session["active_workshop_id"] = workshop.pk
        session.save()
        return workshop

    def test_detail_view_renders_resume_items_on_initial_load(self) -> None:
        workshop = self._login_with_active_workshop(suffix=95)

        customer = create_customer(workshop=workshop, suffix=95)
        vehicle = create_vehicle(workshop=workshop, customer=customer, suffix=95, plate="OSR9595")
        budget = create_budget(workshop=workshop)
        budget.customer = customer
        budget.vehicle = vehicle
        budget.save(update_fields=["customer", "vehicle"])

        direct_product = create_product(workshop=workshop, suffix=951)
        kit_product = create_product(workshop=workshop, suffix=952)
        direct_service = create_service(workshop=workshop, suffix=951)
        kit_service = create_service(workshop=workshop, suffix=952)
        kit = create_kit(workshop=workshop, suffix=9511, products=[(kit_product, 2)])
        KitService.objects.create(kit=kit, service=kit_service, quantity=1, duration=kit_service.duration)

        BudgetItem.objects.create(workshop=workshop, budget=budget, product=direct_product, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, service=direct_service, quantity=1)
        BudgetItem.objects.create(workshop=workshop, budget=budget, kit=kit, quantity=1)

        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.sync_from_budget()

        response = self.client.get(reverse("workorder:workorder_detail", args=[workorder.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("summary_product_items", response.context)
        self.assertIn("summary_service_items", response.context)
        self.assertContains(response, "Ordem de Serviço")
        self.assertContains(response, direct_product.name)
        self.assertContains(response, kit_product.name)
        self.assertContains(response, direct_service.name)
        self.assertContains(response, kit_service.name)
        self.assertContains(response, kit.name)

    def test_resume_section_reflects_updated_item_value_and_disables_cache(self) -> None:
        workshop = self._login_with_active_workshop(suffix=96)
        customer = create_customer(workshop=workshop, suffix=96)
        vehicle = create_vehicle(workshop=workshop, customer=customer, suffix=96, plate="OSR9696")
        budget = create_budget(workshop=workshop)
        budget.customer = customer
        budget.vehicle = vehicle
        budget.save(update_fields=["customer", "vehicle"])

        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        product = create_product(workshop=workshop, suffix=960, selling_price="40.00")
        item = WorkOrderItem.objects.create(workshop=workshop, workorder=workorder, product=product, quantity=1)

        edit_response = self.client.post(
            reverse("workorder:edit_item", args=[workorder.pk, item.pk]),
            {
                "description": item.description,
                "quantity": "1",
                "product_cost_price_0": "10.00",
                "product_cost_price_1": "BRL",
                "product_selling_price_0": "55.00",
                "product_selling_price_1": "BRL",
                "shipping_0": "0.00",
                "shipping_1": "BRL",
                "active_tab": "products",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(edit_response.status_code, 200)

        response = self.client.get(reverse("workorder:resume_section", args=[workorder.pk]), {"_ts": "123"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        self.assertContains(response, "55,00")

    def test_detail_view_shows_reopen_button_and_disables_cancel_reject_for_approved_workorder(self) -> None:
        workshop = self._login_with_active_workshop(suffix=98)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED)

        response = self.client.get(reverse("workorder:workorder_detail", args=[workorder.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reabrir O.S.")
        self.assertContains(response, 'title="Reabra a O.S. antes de alterar o status."', html=False)
        html = response.content.decode("utf-8")
        self.assertRegex(html, r'id="toggle-cancel-workorder-form"[\s\S]*?disabled')
        self.assertRegex(html, r'id="workorder-delivery-button"[\s\S]*?disabled')
        self.assertRegex(html, r'id="toggle-reject-workorder-form"[\s\S]*?disabled')

    def test_detail_view_shows_reopen_button_and_disables_status_buttons_for_cancelled_workorder(self) -> None:
        workshop = self._login_with_active_workshop(suffix=81)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.CANCELLED)

        response = self.client.get(reverse("workorder:workorder_detail", args=[workorder.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reabrir O.S.")
        html = response.content.decode("utf-8")
        self.assertRegex(html, r'id="toggle-cancel-workorder-form"[\s\S]*?disabled')
        self.assertRegex(html, r'id="workorder-delivery-button"[\s\S]*?disabled')
        self.assertRegex(html, r'id="toggle-reject-workorder-form"[\s\S]*?disabled')

    def test_detail_view_shows_reopen_button_and_disables_status_buttons_for_rejected_workorder(self) -> None:
        workshop = self._login_with_active_workshop(suffix=82)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.REJECTED)

        response = self.client.get(reverse("workorder:workorder_detail", args=[workorder.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reabrir O.S.")
        html = response.content.decode("utf-8")
        self.assertRegex(html, r'id="toggle-cancel-workorder-form"[\s\S]*?disabled')
        self.assertRegex(html, r'id="workorder-delivery-button"[\s\S]*?disabled')
        self.assertRegex(html, r'id="toggle-reject-workorder-form"[\s\S]*?disabled')

    def test_detail_view_shows_reopen_button_for_manager(self) -> None:
        manager_user, workshop, _ = create_manager_user_with_workshop(suffix=99)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED)

        self.client.force_login(manager_user)
        session = self.client.session
        session["active_workshop_id"] = workshop.pk
        session.save()

        response = self.client.get(reverse("workorder:workorder_detail", args=[workorder.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reabrir O.S.")


class WorkOrderKitSelectionCompatibilityTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = create_director_user_with_workshop(suffix=97)
        self.client.force_login(self.user)

        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.customer = create_customer(workshop=self.workshop, suffix=97)
        self.vehicle = create_vehicle(
            workshop=self.workshop,
            customer=self.customer,
            suffix=97,
            plate="OSK9797",
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
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget)

        self.compatible_kit = create_kit(
            workshop=self.workshop,
            suffix=9701,
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
        self.no_application_kit = create_kit(workshop=self.workshop, suffix=9702, products=[])
        self.incompatible_kit = create_kit(
            workshop=self.workshop,
            suffix=9703,
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
        response = self.client.get(reverse("workorder:item_selection", args=[self.workorder.pk, "kit"]))

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
            suffix=9704,
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

        response = self.client.get(reverse("workorder:item_selection", args=[self.workorder.pk, "kit"]))

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
            suffix=98,
            plate="OSK9898",
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
        incomplete_workorder = WorkOrder.objects.create(workshop=self.workshop, budget=incomplete_budget)

        response = self.client.get(reverse("workorder:item_selection", args=[incomplete_workorder.pk, "kit"]))

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
            suffix=99,
            plate="OSK9999",
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
        no_match_workorder = WorkOrder.objects.create(workshop=self.workshop, budget=no_match_budget)

        response = self.client.get(reverse("workorder:item_selection", args=[no_match_workorder.pk, "kit"]))

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
            suffix=9705,
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
            suffix=9706,
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

        response = self.client.get(reverse("workorder:item_selection", args=[self.workorder.pk, "kit"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, corolla_kit.name)
        self.assertContains(response, corolla_cross_kit.name)
        self.assertContains(response, '<span class="badge badge-success">Compatível</span>', count=1, html=True)
        self.assertContains(response, "Exibir kits ocultos (4)")
        self.assertContains(response, 'data-hidden-by-kit-filter="true" style="display: none;"', count=4)

    def test_add_items_batch_rejects_incompatible_kit_for_vehicle(self) -> None:
        response = self.client.post(
            reverse("workorder:add_items_batch", args=[self.workorder.pk, "kit"]),
            {"selected_items": [str(self.incompatible_kit.pk)], "active_tab": "kits"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kit indisponível para este veículo")
        self.assertFalse(WorkOrderItem.objects.filter(workorder=self.workorder, kit=self.incompatible_kit).exists())

    def test_add_items_batch_allows_kit_without_applications_as_fallback(self) -> None:
        response = self.client.post(
            reverse("workorder:add_items_batch", args=[self.workorder.pk, "kit"]),
            {"selected_items": [str(self.no_application_kit.pk)], "active_tab": "kits"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(WorkOrderItem.objects.filter(workorder=self.workorder, kit=self.no_application_kit).exists())

    def test_add_items_batch_allows_partially_compatible_kit_for_vehicle(self) -> None:
        partial_kit = create_kit(
            workshop=self.workshop,
            suffix=9704,
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
            reverse("workorder:add_items_batch", args=[self.workorder.pk, "kit"]),
            {"selected_items": [str(partial_kit.pk)], "active_tab": "kits"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(WorkOrderItem.objects.filter(workorder=self.workorder, kit=partial_kit).exists())


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
            ncm="87089990",
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
            ncm="87089990",
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

    def test_pricing_snapshot_uses_traditional_labor_value_when_traditional_method_is_selected(self) -> None:
        workshop = create_workshop(suffix=18)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        service = Service.objects.create(
            workshop=workshop,
            name="Servico Tradicional",
            duration=timedelta(hours=2),
            suggested_cost=Money("40.00", "BRL"),
            selling_price=Money("100.00", "BRL"),
        )
        WorkOrderItem.objects.create(
            workshop=workshop,
            workorder=workorder,
            service=service,
            quantity=1,
        )

        with patch.object(WorkOrder, "calculate_pricing_methods", return_value={"method_name": "Tradicional", "venda_mao_obra": Money("160.00", "BRL")}):
            snapshot = workorder.pricing_snapshot

        self.assertEqual(snapshot.total_services_value, Money("100.00", "BRL"))
        self.assertEqual(snapshot.total_labor_selling_value, Money("160.00", "BRL"))
        self.assertEqual(snapshot.total_labor_by_slider, Money("160.00", "BRL"))
        self.assertEqual(workorder.total_base_value, Money("160.00", "BRL"))

    def test_pricing_snapshot_keeps_hunter_labor_sum_when_hunter_method_is_selected(self) -> None:
        workshop = create_workshop(suffix=19)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        service = Service.objects.create(
            workshop=workshop,
            name="Servico Hunter",
            duration=timedelta(hours=2),
            suggested_cost=Money("40.00", "BRL"),
            selling_price=Money("100.00", "BRL"),
        )
        WorkOrderItem.objects.create(
            workshop=workshop,
            workorder=workorder,
            service=service,
            quantity=1,
        )

        with patch.object(WorkOrder, "calculate_pricing_methods", return_value={"method_name": "Hunter", "venda_mao_obra": Money("160.00", "BRL")}):
            snapshot = workorder.pricing_snapshot

        self.assertEqual(snapshot.total_services_value, Money("100.00", "BRL"))
        self.assertEqual(snapshot.total_labor_selling_value, Money("100.00", "BRL"))
        self.assertEqual(snapshot.total_labor_by_slider, Money("100.00", "BRL"))
        self.assertEqual(workorder.total_base_value, Money("100.00", "BRL"))

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
            ncm="87089990",
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
            ncm="87089990",
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

    def test_signature_preview_renders_workorder_price_when_it_differs_from_budget(self) -> None:
        workshop = create_workshop(suffix=16)
        customer = create_customer(workshop=workshop, suffix=16)
        vehicle = create_vehicle(workshop=workshop, customer=customer, suffix=16, plate="OSP1600")
        budget = create_budget(workshop=workshop)
        budget.customer = customer
        budget.vehicle = vehicle
        budget.save(update_fields=["customer", "vehicle"])

        product = create_product(workshop=workshop, suffix=160, selling_price="60.00")
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=1)

        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.sync_from_budget()
        workorder_item = workorder.items.get()
        workorder_item.product_selling_price = Money("50.00", "BRL")
        workorder_item.save(update_fields=["product_selling_price"])

        token = extract_token_from_url(build_signature_preview_url(workorder=workorder))
        response = self.client.get(reverse("workorder:signature_preview", args=[token]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "50,00")
        self.assertNotContains(response, "60,00")


class WorkOrderPdfParityTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_build_workorder_pdf_render_request_uses_workorder_values_in_pdf_context(self) -> None:
        workshop = create_workshop(suffix=99)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=999, selling_price="60.00")
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=1)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.sync_from_budget()
        workorder_item = workorder.items.get()
        workorder_item.product_selling_price = Money("50.00", "BRL")
        workorder_item.save(update_fields=["product_selling_price"])
        filename = "documento.pdf"

        workorder_render_request = build_workorder_pdf_render_request(workorder=workorder, filename=filename)

        self.assertEqual(workorder_render_request.template_name, "workorder/partials/pdf/visualizarPDF.html")
        self.assertEqual(workorder_render_request.filename, filename)
        self.assertEqual(workorder_render_request.context["workorder"], workorder)
        self.assertEqual(workorder_render_request.context["budget"].id, workorder.get_id)
        self.assertEqual(workorder_render_request.context["budget"].resolved_discount_value, workorder.pricing_snapshot.resolved_discount_value)
        self.assertEqual(workorder_render_request.context["pages"][0]["produtos"][0]["unit_price"], Money("50.00", "BRL"))
        self.assertEqual(workorder_render_request.context["pages"][0]["produtos"][0]["total_price"], Money("50.00", "BRL"))

    def test_build_workorder_pdf_render_request_uses_workorder_filename_by_default(self) -> None:
        workshop = create_workshop(suffix=89)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        render_request = build_workorder_pdf_render_request(workorder=workorder)

        self.assertEqual(render_request.filename, f"ordem_servico_{workorder.get_id}.pdf")


class WorkOrderInternalPdfTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @patch("apps.workorder.views.get_active_workshop_or_404")
    @patch("apps.workorder.views.render_workorder_pdf_document")
    @patch("apps.workorder.views.download_signed_document_content")
    def test_visualizar_pdf_workorder_variant_base_skips_signed_download(self, download_signed_mock, render_document_mock, active_workshop_mock) -> None:
        workshop = create_workshop(suffix=86)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.signature_request_status = WorkOrderSignatureStatus.APPROVED
        workorder.signature_external_id = "env-86"
        workorder.signature_document_id = "doc-86"
        workorder.save(update_fields=["signature_request_status", "signature_external_id", "signature_document_id"])

        active_workshop_mock.return_value = workshop
        render_document_mock.return_value = DocumentPayload(
            content=b"%PDF-base",
            filename=f"ordem_servico_{workorder.get_id}_base.pdf",
        )

        response = visualizar_pdf_workorder(self.factory.get("/", {"variant": "base", "download": "1"}), workorder.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-base")
        download_signed_mock.assert_not_called()

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
            filename=f"ordem_servico_{workorder.get_id}_base.pdf",
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
            filename=f"ordem_servico_{workorder.get_id}.pdf",
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
        self.assertEqual(kwargs["file_name"], f"ordem_servico-{workorder.get_id}.pdf")
        self.assertEqual(kwargs["document_ref_id"], f"workorder-{workorder.id}")
        self.assertEqual(kwargs["title"], f"Ordem de servico #{workorder.get_id}")
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
            ncm="87089990",
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

    def test_workorder_item_uses_kit_service_custom_selling_price(self) -> None:
        workshop = create_workshop(suffix=13)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        service = create_service(workshop=workshop, suffix=130)
        kit = create_kit(workshop=workshop, suffix=1301, products=[])
        KitService.objects.create(kit=kit, service=service, quantity=2, duration=service.duration, selling_price=Money("33.00", "BRL"))

        item = WorkOrderItem.objects.create(workshop=workshop, workorder=workorder, kit=kit, quantity=1)

        self.assertEqual(item.service_selling_price, Money("66.00", "BRL"))
        self.assertEqual(item.get_kit_services_total(), Money("66.00", "BRL"))

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

    def test_approval_blocks_when_product_has_invalid_ncm(self) -> None:
        workshop = create_workshop(suffix=13)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=13)
        product.ncm = ""
        product.save(update_fields=["ncm"])
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=1)

        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.sync_from_budget()

        stock_product = StockProduct.objects.get(workshop=workshop, product=product)
        stock_product.current_quantity = 5
        stock_product.save(update_fields=["current_quantity"])

        with self.assertRaisesMessage(WorkOrderApprovalError, "Existem produtos com NCM invalido"):
            approve_workorder_with_stock(workorder=workorder)

        stock_product.refresh_from_db()
        workorder.refresh_from_db()
        self.assertEqual(stock_product.current_quantity, 5)
        self.assertEqual(workorder.status, WorkOrderStatus.DRAFT)


class WorkOrderSignatureWorkflowRuleTests(TestCase):
    @patch("apps.workorder.util.send_workorder_for_signature")
    def test_signature_send_blocks_for_stock_issue(self, send_signature_mock) -> None:
        workshop = create_workshop(suffix=14)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=14)
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=2)

        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.sync_from_budget()

        stock_product = StockProduct.objects.get(workshop=workshop, product=product)
        stock_product.current_quantity = 1
        stock_product.save(update_fields=["current_quantity"])

        toast_type, toast_message = trigger_workorder_signature_send_if_needed(workorder=workorder)

        self.assertEqual(toast_type, "error")
        self.assertIn("Existem pecas com quantidade acima do estoque disponivel", toast_message)
        send_signature_mock.assert_not_called()

    @patch("apps.workorder.util.send_workorder_for_signature")
    def test_signature_send_allows_invalid_ncm(self, send_signature_mock) -> None:
        workshop = create_workshop(suffix=15)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=15)
        product.ncm = ""
        product.save(update_fields=["ncm"])
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=1)

        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.sync_from_budget()

        stock_product = StockProduct.objects.get(workshop=workshop, product=product)
        stock_product.current_quantity = 3
        stock_product.save(update_fields=["current_quantity"])
        payment_method = PaymentMethod.objects.create(workshop=workshop, description="Pix", installments_count=1)
        WorkOrderPaymentMethod.objects.create(
            workorder=workorder,
            payment_method=payment_method,
            first_installment_amount=workorder.total_budget_value,
            remaining_installments_amount=Money("0.00", "BRL"),
            installments_count=1,
            due_date=date(2026, 3, 20),
        )

        send_signature_mock.return_value = SignatureDeliveryResult(
            envelope_id="env-15",
            document_id="doc-15",
            provider="supersign",
            raw_response={"ok": True},
        )

        toast_type, toast_message = trigger_workorder_signature_send_if_needed(workorder=workorder)

        workorder.refresh_from_db()
        self.assertEqual(toast_type, "success")
        self.assertEqual(toast_message, "Ordem de serviço enviada para assinatura do cliente.")
        self.assertEqual(workorder.signature_request_status, WorkOrderSignatureStatus.SENT)

    @patch("apps.workorder.util.send_workorder_for_signature")
    def test_signature_send_blocks_when_payment_is_pending(self, send_signature_mock) -> None:
        workshop = create_workshop(suffix=16)
        budget = create_budget(workshop=workshop)
        product = create_product(workshop=workshop, suffix=16, selling_price="100.00")
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=1)

        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.sync_from_budget()

        toast_type, toast_message = trigger_workorder_signature_send_if_needed(workorder=workorder)

        self.assertEqual(toast_type, "error")
        self.assertIn("Receba o pagamento integral da ordem de serviço", toast_message)
        send_signature_mock.assert_not_called()


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
                "entry_amount_0": "40.00",
                "entry_amount_1": "BRL",
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
                "entry_amount_0": "100.00",
                "entry_amount_1": "BRL",
                "due_date": "2026-03-21",
            },
            workorder=self.workorder,
        )

        self.assertTrue(form.is_valid(), form.errors)
        payment = form.save(commit=False)
        payment.workorder = self.workorder
        payment.save()

        self.assertEqual(payment.total_paid, Money("100.00", "BRL"))

    def test_form_allows_paying_rounded_full_total_with_subcent_raw_total(self) -> None:
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix Subcent", installments_count=1)

        with patch.object(WorkOrder, "total_budget_value", new_callable=PropertyMock) as total_budget_value_mock:
            total_budget_value_mock.return_value = Money(Decimal("99.996"), "BRL")
            form = WorkOrderPaymentForm(
                data={
                    "payment_method": str(payment_method.pk),
                    "entry_amount_0": "100.00",
                    "entry_amount_1": "BRL",
                    "due_date": "2026-03-21",
                },
                workorder=self.workorder,
            )
            self.assertTrue(form.is_valid(), form.errors)

    def test_pending_payment_value_ignores_subcent_residual_after_full_cent_payment(self) -> None:
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix Residual", installments_count=1)
        WorkOrderPaymentMethod.objects.create(
            workorder=self.workorder,
            payment_method=payment_method,
            first_installment_amount=Money("100.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            installments_count=1,
            due_date=date(2026, 3, 21),
        )

        with patch.object(WorkOrder, "total_budget_value", new_callable=PropertyMock) as total_budget_value_mock:
            total_budget_value_mock.return_value = Money(Decimal("100.004"), "BRL")
            self.assertEqual(self.workorder.pending_payment_value, Money("0.00", "BRL"))
            self.assertTrue(self.workorder.is_fully_paid)

    def test_form_defaults_due_date_to_today_when_not_provided(self) -> None:
        self._set_workorder_total("100.00", suffix=23)
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix", installments_count=1)

        form = WorkOrderPaymentForm(
            data={
                "payment_method": str(payment_method.pk),
                "entry_amount_0": "50.00",
                "entry_amount_1": "BRL",
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
                "entry_amount_0": "100.01",
                "entry_amount_1": "BRL",
                "due_date": "2026-03-22",
            },
            workorder=self.workorder,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("O valor de entrada não pode exceder o saldo pendente", str(form.errors["entry_amount"][0]))

    def test_form_uses_valor_a_ser_pago_for_additional_payments(self) -> None:
        self._set_workorder_total("100.00", suffix=29)
        first_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix", installments_count=1)
        second_method = PaymentMethod.objects.create(workshop=self.workshop, description="Cartão", installments_count=2)

        WorkOrderPaymentMethod.objects.create(
            workorder=self.workorder,
            payment_method=first_method,
            first_installment_amount=Money("20.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            installments_count=1,
            due_date=date(2026, 3, 20),
        )

        form = WorkOrderPaymentForm(
            data={
                "payment_method": str(second_method.pk),
                "entry_amount_0": "80.00",
                "entry_amount_1": "BRL",
                "first_installment_amount_0": "30.00",
                "first_installment_amount_1": "BRL",
                "due_date": "2026-03-22",
            },
            workorder=self.workorder,
        )

        self.assertTrue(form.fields["entry_amount"].disabled)
        self.assertFalse(form.fields["first_installment_amount"].disabled)
        self.assertTrue(form.is_valid(), form.errors)

        payment = form.save(commit=False)
        payment.workorder = self.workorder
        payment.save()

        self.assertEqual(payment.first_installment_amount, Money("30.00", "BRL"))
        self.assertEqual(payment.total_paid, Money("30.00", "BRL"))


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
                "entry_amount_0": "40.00",
                "entry_amount_1": "BRL",
                "due_date": "2026-03-24",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cartão Master/Visa")
        self.assertContains(response, "24/03/2026")
        self.assertContains(response, "Valor de entrada")
        self.assertContains(response, "Valor a ser pago")
        self.assertContains(response, "Pago")
        self.assertContains(response, "alert_confirm_modal")
        self.assertContains(response, 'data-confirm="Deseja remover esta forma de pagamento?"', html=False)
        self.assertContains(response, 'id="resume-section" hx-swap-oob="innerHTML"', html=False)
        self.assertContains(response, 'id="customer-approvement-section" hx-swap-oob="innerHTML"', html=False)

        payment = WorkOrderPaymentMethod.objects.get(workorder=self.workorder)
        self.assertEqual(payment.installments_count, 4)
        self.assertEqual(payment.remaining_installments_amount, Money("0.00", "BRL"))
        self.assertEqual(payment.total_paid, Money("40.00", "BRL"))
        self.assertEqual(payment.due_date, date(2026, 3, 24))

    def test_post_with_existing_payments_uses_valor_a_ser_pago(self) -> None:
        first_method = PaymentMethod.objects.create(workshop=self.workshop, description="Dinheiro", installments_count=1)
        second_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix", installments_count=1)
        WorkOrderPaymentMethod.objects.create(
            workorder=self.workorder,
            payment_method=first_method,
            first_installment_amount=Money("30.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            installments_count=1,
            due_date=date(2026, 3, 20),
        )

        response = self.client.post(
            reverse("workorder:add_payment", args=[self.workorder.pk]),
            data={
                "payment_method": str(second_method.pk),
                "first_installment_amount_0": "20.00",
                "first_installment_amount_1": "BRL",
                "due_date": "2026-03-24",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkOrderPaymentMethod.objects.filter(workorder=self.workorder).count(), 2)
        last_payment = WorkOrderPaymentMethod.objects.filter(workorder=self.workorder).order_by("-pk").first()
        self.assertIsNotNone(last_payment)
        self.assertEqual(last_payment.first_installment_amount, Money("20.00", "BRL"))

    def test_post_with_existing_paid_plan_keeps_each_payment_status_independent(self) -> None:
        first_method = PaymentMethod.objects.create(workshop=self.workshop, description="Dinheiro", installments_count=1)
        second_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix", installments_count=1)
        first_payment = WorkOrderPaymentMethod.objects.create(
            workorder=self.workorder,
            payment_method=first_method,
            first_installment_amount=Money("30.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            installments_count=1,
            due_date=date(2026, 3, 20),
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            workorder=self.workorder,
            workorder_payment=first_payment,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("30.00", "BRL"),
            due_date=date(2026, 3, 20),
            is_paid=True,
        )

        response = self.client.post(
            reverse("workorder:add_payment", args=[self.workorder.pk]),
            data={
                "payment_method": str(second_method.pk),
                "first_installment_amount_0": "20.00",
                "first_installment_amount_1": "BRL",
                "due_date": "2026-03-24",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertRegex(html, r"Dinheiro[\s\S]*?Pago")
        self.assertRegex(html, r"Pix[\s\S]*?Pago")

    def test_payment_section_shows_success_when_workorder_is_fully_paid(self) -> None:
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix", installments_count=1)
        WorkOrderPaymentMethod.objects.create(
            workorder=self.workorder,
            payment_method=payment_method,
            first_installment_amount=self.workorder.total_budget_value,
            remaining_installments_amount=Money("0.00", "BRL"),
            installments_count=1,
            due_date=date(2026, 3, 24),
        )

        response = self.client.get(reverse("workorder:payment_section", args=[self.workorder.pk]), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ordem de Serviço completamente paga")
        self.assertContains(response, "A ordem de serviço foi paga completamente.")
        self.assertContains(response, "alert-success")
        self.assertContains(response, "check_circle")
        self.assertContains(response, 'title="OS paga por completo"', html=False)

    def test_payment_section_uses_financial_movement_paid_status_badge(self) -> None:
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix", installments_count=1)
        payment = WorkOrderPaymentMethod.objects.create(
            workorder=self.workorder,
            payment_method=payment_method,
            first_installment_amount=Money("100.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            installments_count=1,
            due_date=date(2026, 3, 24),
        )
        FinancialMovement.objects.create(
            workshop=self.workshop,
            user=self.user,
            workorder=self.workorder,
            movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            direction=FinancialMovement.MovementDirection.CREDIT,
            amount=Money("100.00", "BRL"),
            due_date=date(2026, 3, 24),
            is_paid=False,
        )

        response = self.client.get(reverse("workorder:payment_section", args=[self.workorder.pk]), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, payment.payment_method.description)
        self.assertContains(response, "Pendente")
        self.assertContains(response, "badge-warning")

        html = response.content.decode()
        self.assertRegex(html, r'id="id_entry_amount_0_display"[\s\S]*?disabled[\s\S]*?>')
        self.assertRegex(html, r'id="id_first_installment_amount_0_display"[\s\S]*?disabled[\s\S]*?>')
        self.assertRegex(html, r'id="id_payment_method"[\s\S]*?disabled[\s\S]*?>')
        self.assertRegex(html, r'placeholder="Digite para buscar\.\.\."[\s\S]*?title="OS paga por completo"[\s\S]*?disabled[\s\S]*?>')
        self.assertRegex(html, r'id="id_due_date"[\s\S]*?title="OS paga por completo"[\s\S]*?disabled[\s\S]*?>')
        self.assertGreaterEqual(html.count('title="OS paga por completo"'), 8)
        self.assertLess(html.index('id="payment-success-workorder-js"'), html.index('id="id_entry_amount_0_display"'))
        self.assertLess(html.index('id="id_due_date"'), html.index('id="payment-warning-workorder-js"'))
        self.assertLess(html.index('id="payment-warning-workorder-js"'), html.index("Salvar Plano de Pagamento"))
        self.assertIn('id="payment-warning-workorder-js" class="hidden', html)

    def test_update_discount_syncs_budget_and_rerenders_payment_section(self) -> None:
        BudgetItem.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            product=self.workorder.items.first().product,
            quantity=1,
        )
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix", installments_count=1)
        WorkOrderPaymentMethod.objects.create(
            workorder=self.workorder,
            payment_method=payment_method,
            first_installment_amount=Money("40.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            installments_count=1,
            due_date=date(2026, 3, 24),
        )

        response = self.client.post(
            reverse("workorder:update_discount", args=[self.workorder.pk]),
            data={"discount_percentage": "0.10", "discount_value_0": "0.00"},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()
        self.budget.refresh_from_db()
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/json"))
        self.assertTrue(payload["ok"])
        self.assertIn("discount_value", payload)
        self.assertEqual(self.workorder.discount_value, Money("10.00", "BRL"))
        self.assertEqual(self.budget.discount_value, Money("10.00", "BRL"))
        self.assertEqual(self.budget.discount_percentage, Decimal("0.100000"))
        self.assertEqual(payload["total_budget_value"], "90.00")
        self.assertEqual(payload["paid_value"], "40.00")
        self.assertEqual(payload["pending_value"], "50.00")
        self.assertTrue(payload["has_completion_blockers"])
        self.assertIn("Receba o pagamento integral", payload["completion_blockers_display"])

    def test_update_km_final_persists_value_without_changing_status(self) -> None:
        customer = create_customer(workshop=self.workshop, suffix=241)
        vehicle = create_vehicle(workshop=self.workshop, customer=customer, suffix=241)
        self.budget.customer = customer
        self.budget.vehicle = vehicle
        self.budget.current_km = 12000
        self.budget.save(update_fields=["customer", "vehicle", "current_km"])

        response = self.client.post(
            reverse("workorder:update_km_final", args=[self.workorder.pk]),
            data={"km_final": "12550"},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()
        vehicle.refresh_from_db()
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/json"))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["km_final"], 12550)
        self.assertEqual(self.workorder.km_final, 12550)
        self.assertEqual(self.workorder.status, WorkOrderStatus.DRAFT)
        self.assertIsNone(self.workorder.delivered_at)
        self.assertIsNone(vehicle.km)

    def test_update_km_final_rejects_value_lower_than_initial_km(self) -> None:
        customer = create_customer(workshop=self.workshop, suffix=242)
        vehicle = create_vehicle(workshop=self.workshop, customer=customer, suffix=242)
        self.budget.customer = customer
        self.budget.vehicle = vehicle
        self.budget.current_km = 12000
        self.budget.save(update_fields=["customer", "vehicle", "current_km"])

        response = self.client.post(
            reverse("workorder:update_km_final", args=[self.workorder.pk]),
            data={"km_final": "11999"},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()
        payload = json.loads(response.content)

        self.assertEqual(response.status_code, 400)
        self.assertTrue(response["Content-Type"].startswith("application/json"))
        self.assertFalse(payload["ok"])
        self.assertIn("KM inicial (12.000)", payload["errors"][0])
        self.assertIsNone(self.workorder.km_final)
        self.assertEqual(self.workorder.status, WorkOrderStatus.DRAFT)

    def test_approve_status_persists_delivered_at(self) -> None:
        customer = create_customer(workshop=self.workshop, suffix=243)
        vehicle = create_vehicle(workshop=self.workshop, customer=customer, suffix=243)
        product = create_product(workshop=self.workshop, suffix=243)
        BudgetItem.objects.create(workshop=self.workshop, budget=self.budget, product=product, quantity=1)
        stock_product = StockProduct.objects.get(workshop=self.workshop, product=product)
        stock_product.current_quantity = 5
        stock_product.save(update_fields=["current_quantity"])
        self.workorder.sync_from_budget()
        self.budget.customer = customer
        self.budget.vehicle = vehicle
        self.budget.current_km = 12000
        self.budget.save(update_fields=["customer", "vehicle", "current_km"])
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix", installments_count=1)
        WorkOrderPaymentMethod.objects.create(
            workorder=self.workorder,
            payment_method=payment_method,
            first_installment_amount=self.workorder.total_budget_value,
            remaining_installments_amount=Money("0.00", "BRL"),
            installments_count=1,
            due_date=date(2026, 3, 24),
        )

        response = self.client.post(
            reverse("workorder:update_status", args=[self.workorder.pk, "approve"]),
            data={
                "km_final": "12500",
                "unsigned_delivery_reason": "Cliente retirou presencialmente e autorizou verbalmente.",
            },
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertEqual(self.workorder.status, WorkOrderStatus.APPROVED)
        self.assertIsNotNone(self.workorder.delivered_at)
        self.assertEqual(self.workorder.unsigned_delivery_reason, "Cliente retirou presencialmente e autorizou verbalmente.")

    def test_approve_status_requires_reason_when_signature_is_pending(self) -> None:
        customer = create_customer(workshop=self.workshop, suffix=245)
        vehicle = create_vehicle(workshop=self.workshop, customer=customer, suffix=245)
        product = create_product(workshop=self.workshop, suffix=245)
        BudgetItem.objects.create(workshop=self.workshop, budget=self.budget, product=product, quantity=1)
        stock_product = StockProduct.objects.get(workshop=self.workshop, product=product)
        stock_product.current_quantity = 5
        stock_product.save(update_fields=["current_quantity"])
        self.workorder.sync_from_budget()
        self.budget.customer = customer
        self.budget.vehicle = vehicle
        self.budget.current_km = 12000
        self.budget.save(update_fields=["customer", "vehicle", "current_km"])
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix", installments_count=1)
        WorkOrderPaymentMethod.objects.create(
            workorder=self.workorder,
            payment_method=payment_method,
            first_installment_amount=self.workorder.total_budget_value,
            remaining_installments_amount=Money("0.00", "BRL"),
            installments_count=1,
            due_date=date(2026, 3, 24),
        )

        response = self.client.post(
            reverse("workorder:update_status", args=[self.workorder.pk, "approve"]),
            data={"km_final": "12500", "unsigned_delivery_reason": ""},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.workorder.status, WorkOrderStatus.DRAFT)
        self.assertContains(response, "Informe a justificativa para entregar o veículo sem a assinatura da O.S.")

    def test_approval_form_does_not_require_reason_when_signature_is_approved(self) -> None:
        self.workorder.signature_request_status = WorkOrderSignatureStatus.APPROVED
        self.workorder.save(update_fields=["signature_request_status"])

        form = WorkOrderCustomerApprovalForm(data={"km_final": "12500", "unsigned_delivery_reason": ""}, workorder=self.workorder)

        self.assertTrue(form.is_valid())

    def test_approve_status_allows_delivery_without_reason_when_signature_is_approved(self) -> None:
        customer = create_customer(workshop=self.workshop, suffix=246)
        vehicle = create_vehicle(workshop=self.workshop, customer=customer, suffix=246)
        product = create_product(workshop=self.workshop, suffix=246)
        BudgetItem.objects.create(workshop=self.workshop, budget=self.budget, product=product, quantity=1)
        stock_product = StockProduct.objects.get(workshop=self.workshop, product=product)
        stock_product.current_quantity = 5
        stock_product.save(update_fields=["current_quantity"])
        self.workorder.sync_from_budget()
        self.workorder.signature_request_status = WorkOrderSignatureStatus.APPROVED
        self.workorder.save(update_fields=["signature_request_status"])
        self.budget.customer = customer
        self.budget.vehicle = vehicle
        self.budget.current_km = 12000
        self.budget.save(update_fields=["customer", "vehicle", "current_km"])
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix", installments_count=1)
        WorkOrderPaymentMethod.objects.create(
            workorder=self.workorder,
            payment_method=payment_method,
            first_installment_amount=self.workorder.total_budget_value,
            remaining_installments_amount=Money("0.00", "BRL"),
            installments_count=1,
            due_date=date(2026, 3, 24),
        )

        response = self.client.post(
            reverse("workorder:update_status", args=[self.workorder.pk, "approve"]),
            data={"km_final": "12500", "unsigned_delivery_reason": ""},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertEqual(self.workorder.status, WorkOrderStatus.APPROVED)
        self.assertEqual(self.workorder.unsigned_delivery_reason, "")

    def test_approve_status_blocks_delivery_when_payment_is_pending(self) -> None:
        customer = create_customer(workshop=self.workshop, suffix=244)
        vehicle = create_vehicle(workshop=self.workshop, customer=customer, suffix=244)
        product = create_product(workshop=self.workshop, suffix=244, selling_price="120.00")
        BudgetItem.objects.create(workshop=self.workshop, budget=self.budget, product=product, quantity=1)
        stock_product = StockProduct.objects.get(workshop=self.workshop, product=product)
        stock_product.current_quantity = 5
        stock_product.save(update_fields=["current_quantity"])
        self.workorder.sync_from_budget()
        self.budget.customer = customer
        self.budget.vehicle = vehicle
        self.budget.current_km = 12000
        self.budget.save(update_fields=["customer", "vehicle", "current_km"])

        response = self.client.post(
            reverse("workorder:update_status", args=[self.workorder.pk, "approve"]),
            data={"km_final": "12500"},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.workorder.status, WorkOrderStatus.DRAFT)
        self.assertIsNone(self.workorder.delivered_at)
        self.assertIn("showToast", response.headers.get("HX-Trigger", ""))

    def test_status_reason_form_requires_reason_for_cancel(self) -> None:
        form = WorkOrderStatusReasonForm(data={"status_reason": "   "}, workorder=self.workorder, action="cancel")

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["status_reason"], ["Informe a justificativa para cancelar a O.S."])

    def test_cancel_status_requires_reason(self) -> None:
        response = self.client.post(
            reverse("workorder:update_status", args=[self.workorder.pk, "cancel"]),
            data={"status_reason": ""},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.workorder.status, WorkOrderStatus.DRAFT)
        self.assertContains(response, "Informe a justificativa para cancelar a O.S.")

    def test_cancel_status_persists_reason(self) -> None:
        response = self.client.post(
            reverse("workorder:update_status", args=[self.workorder.pk, "cancel"]),
            data={"status_reason": "Cliente desistiu do serviço antes da execução."},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertEqual(self.workorder.status, WorkOrderStatus.CANCELLED)
        self.assertEqual(self.workorder.cancellation_reason, "Cliente desistiu do serviço antes da execução.")

    def test_reject_status_requires_reason(self) -> None:
        response = self.client.post(
            reverse("workorder:update_status", args=[self.workorder.pk, "reject"]),
            data={"status_reason": ""},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.workorder.status, WorkOrderStatus.DRAFT)
        self.assertContains(response, "Informe a justificativa para reprovar a O.S.")

    def test_reject_status_persists_reason(self) -> None:
        response = self.client.post(
            reverse("workorder:update_status", args=[self.workorder.pk, "reject"]),
            data={"status_reason": "Serviço recusado após análise técnica."},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertEqual(self.workorder.status, WorkOrderStatus.REJECTED)
        self.assertEqual(self.workorder.rejection_reason, "Serviço recusado após análise técnica.")

    def test_reject_status_is_blocked_after_cancellation(self) -> None:
        self.workorder.status = WorkOrderStatus.CANCELLED
        self.workorder.cancellation_reason = "Cliente desistiu."
        self.workorder.save(update_fields=["status", "cancellation_reason"])

        response = self.client.post(
            reverse("workorder:update_status", args=[self.workorder.pk, "reject"]),
            data={"status_reason": "Tentativa posterior."},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.workorder.status, WorkOrderStatus.CANCELLED)
        self.assertIn("Reabrir O.S.", response.content.decode("utf-8"))
        self.assertIn("showToast", response.headers.get("HX-Trigger", ""))

    def test_approve_status_is_blocked_after_cancellation(self) -> None:
        self.workorder.status = WorkOrderStatus.CANCELLED
        self.workorder.cancellation_reason = "Cliente desistiu."
        self.workorder.save(update_fields=["status", "cancellation_reason"])

        response = self.client.post(
            reverse("workorder:update_status", args=[self.workorder.pk, "approve"]),
            data={"km_final": "12500"},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.workorder.status, WorkOrderStatus.CANCELLED)
        self.assertIsNone(self.workorder.delivered_at)
        self.assertIn("showToast", response.headers.get("HX-Trigger", ""))

    def test_cancel_status_is_blocked_after_rejection(self) -> None:
        self.workorder.status = WorkOrderStatus.REJECTED
        self.workorder.rejection_reason = "Cliente rejeitou."
        self.workorder.save(update_fields=["status", "rejection_reason"])

        response = self.client.post(
            reverse("workorder:update_status", args=[self.workorder.pk, "cancel"]),
            data={"status_reason": "Tentativa posterior."},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.workorder.status, WorkOrderStatus.REJECTED)
        self.assertIn("Reabrir O.S.", response.content.decode("utf-8"))
        self.assertIn("showToast", response.headers.get("HX-Trigger", ""))

    def test_approve_status_is_blocked_after_rejection(self) -> None:
        self.workorder.status = WorkOrderStatus.REJECTED
        self.workorder.rejection_reason = "Cliente rejeitou."
        self.workorder.save(update_fields=["status", "rejection_reason"])

        response = self.client.post(
            reverse("workorder:update_status", args=[self.workorder.pk, "approve"]),
            data={"km_final": "12500"},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.workorder.status, WorkOrderStatus.REJECTED)
        self.assertIsNone(self.workorder.delivered_at)
        self.assertIn("showToast", response.headers.get("HX-Trigger", ""))

    def test_cancel_status_is_blocked_after_delivery(self) -> None:
        self.workorder.status = WorkOrderStatus.APPROVED
        self.workorder.delivered_at = timezone.now()
        self.workorder.save(update_fields=["status", "delivered_at"])

        response = self.client.post(
            reverse("workorder:update_status", args=[self.workorder.pk, "cancel"]),
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.workorder.status, WorkOrderStatus.APPROVED)
        self.assertIn("Reabrir O.S.", response.content.decode("utf-8"))
        self.assertIn("showToast", response.headers.get("HX-Trigger", ""))

    def test_reject_status_is_blocked_after_delivery(self) -> None:
        self.workorder.status = WorkOrderStatus.APPROVED
        self.workorder.delivered_at = timezone.now()
        self.workorder.save(update_fields=["status", "delivered_at"])

        response = self.client.post(
            reverse("workorder:update_status", args=[self.workorder.pk, "reject"]),
            data={"status_reason": "Tentativa posterior."},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.workorder.status, WorkOrderStatus.APPROVED)
        self.assertIn("showToast", response.headers.get("HX-Trigger", ""))

    def test_approve_status_is_blocked_after_delivery(self) -> None:
        delivered_at = timezone.now()
        self.workorder.status = WorkOrderStatus.APPROVED
        self.workorder.delivered_at = delivered_at
        self.workorder.save(update_fields=["status", "delivered_at"])

        response = self.client.post(
            reverse("workorder:update_status", args=[self.workorder.pk, "approve"]),
            data={"km_final": "12500"},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.workorder.status, WorkOrderStatus.APPROVED)
        self.assertEqual(self.workorder.delivered_at, delivered_at)
        self.assertIn("showToast", response.headers.get("HX-Trigger", ""))

    def test_reopen_status_requires_reason_and_reverts_stock_and_deletes_financial_movements(self) -> None:
        customer = create_customer(workshop=self.workshop, suffix=247)
        vehicle = create_vehicle(workshop=self.workshop, customer=customer, suffix=247)
        product = create_product(workshop=self.workshop, suffix=247, selling_price="120.00")
        BudgetItem.objects.create(workshop=self.workshop, budget=self.budget, product=product, quantity=1)
        stock_product = StockProduct.objects.get(workshop=self.workshop, product=product)
        stock_product.current_quantity = 5
        stock_product.save(update_fields=["current_quantity"])
        self.workorder.sync_from_budget()
        self.budget.customer = customer
        self.budget.vehicle = vehicle
        self.budget.current_km = 12000
        self.budget.status = "approved"
        self.budget.save(update_fields=["customer", "vehicle", "current_km", "status"])
        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix", installments_count=1)
        WorkOrderPaymentMethod.objects.create(
            workorder=self.workorder,
            payment_method=payment_method,
            first_installment_amount=self.workorder.total_budget_value,
            remaining_installments_amount=Money("0.00", "BRL"),
            installments_count=1,
            due_date=date(2026, 3, 24),
        )

        self.client.post(
            reverse("workorder:update_status", args=[self.workorder.pk, "approve"]),
            data={"km_final": "12500", "unsigned_delivery_reason": "Cliente retirou sem assinar."},
            HTTP_HX_REQUEST="true",
        )
        self.workorder.refresh_from_db()
        stock_product.refresh_from_db()
        original_stock_movement = StockMovement.objects.get(workorder=self.workorder, type=StockMovement.MovementType.EXIT)
        original_financial_movement_ids = list(
            FinancialMovement.objects.filter(
                workorder=self.workorder,
                movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
            ).values_list("pk", flat=True)
        )

        invalid_response = self.client.post(
            reverse("workorder:reopen", args=[self.workorder.pk]),
            data={"reopen_reason": ""},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(invalid_response.status_code, 200)
        self.assertContains(invalid_response, "Informe a justificativa para reabrir a O.S.")

        response = self.client.post(
            reverse("workorder:reopen", args=[self.workorder.pk]),
            data={"reopen_reason": "Cliente pediu reexecução do serviço."},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()
        stock_product.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertEqual(self.workorder.status, WorkOrderStatus.DRAFT)
        self.assertIsNone(self.workorder.delivered_at)
        self.assertEqual(self.workorder.reopen_reason, "Cliente pediu reexecução do serviço.")
        self.assertEqual(stock_product.current_quantity, 5)

        history_entry = WorkOrderHistory.objects.get(workorder=self.workorder, action=WorkOrderHistory.Action.REOPENED)
        self.assertEqual(history_entry.reason, "Cliente pediu reexecução do serviço.")

        reversal_stock = StockMovement.objects.get(reversal_of=original_stock_movement)
        self.assertEqual(reversal_stock.type, StockMovement.MovementType.ENTRY)
        self.assertEqual(reversal_stock.quantity, 1)

        self.assertFalse(FinancialMovement.objects.filter(pk__in=original_financial_movement_ids).exists())
        self.assertFalse(
            FinancialMovement.objects.filter(
                workorder=self.workorder,
                movement_kind__in=[
                    FinancialMovement.MovementKind.WORKORDER_PARENT,
                    FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
                ],
            ).exists()
        )

        detail_response = self.client.get(reverse("workorder:workorder_detail", args=[self.workorder.pk]))
        self.assertContains(detail_response, "Histórico da OS")
        self.assertContains(detail_response, "Cliente pediu reexecução do serviço.")
        self.assertContains(detail_response, timezone.localtime(history_entry.criado_em).strftime("%d/%m/%Y %H:%M"))

    def test_reopen_and_reapprove_do_not_duplicate_payment_or_card_fee_movements(self) -> None:
        customer = create_customer(workshop=self.workshop, suffix=548)
        vehicle = create_vehicle(workshop=self.workshop, customer=customer, suffix=548)
        self.budget.customer = customer
        self.budget.vehicle = vehicle
        self.budget.current_km = 15000
        self.budget.status = "approved"
        self.budget.problem_description = "Reparo com reabertura"
        self.budget.save(update_fields=["customer", "vehicle", "current_km", "status", "problem_description"])
        self.workorder.sync_from_budget()

        card_method = PaymentMethod.objects.create(workshop=self.workshop, description="Cartão", installments_count=1, tax_percentage=Decimal("2.50"))
        WorkOrderPaymentMethod.objects.create(
            workorder=self.workorder,
            payment_method=card_method,
            first_installment_amount=Money("100.00", "BRL"),
            remaining_installments_amount=Money("0.00", "BRL"),
            installments_count=1,
            due_date=date(2026, 3, 24),
        )

        def _approve() -> None:
            response = self.client.post(
                reverse("workorder:update_status", args=[self.workorder.pk, "approve"]),
                data={"km_final": "15100", "unsigned_delivery_reason": "Entrega sem assinatura."},
                HTTP_HX_REQUEST="true",
            )
            self.assertEqual(response.status_code, 200)

        def _reopen(reason: str) -> None:
            response = self.client.post(
                reverse("workorder:reopen", args=[self.workorder.pk]),
                data={"reopen_reason": reason},
                HTTP_HX_REQUEST="true",
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("HX-Refresh"), "true")

        reversed_ids = FinancialMovement.objects.filter(reversal_of__isnull=False).values_list("reversal_of_id", flat=True)

        def _active_parent_payment_count() -> int:
            return (
                FinancialMovement.objects.filter(
                    workorder=self.workorder,
                    movement_kind=FinancialMovement.MovementKind.WORKORDER_PARENT,
                    workorder_payment__isnull=False,
                    reversal_of__isnull=True,
                )
                .exclude(pk__in=reversed_ids)
                .count()
            )

        def _active_card_fee_count() -> int:
            return (
                FinancialMovement.objects.filter(
                    workorder=self.workorder,
                    movement_kind=FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
                    reversal_of__isnull=True,
                )
                .exclude(pk__in=reversed_ids)
                .count()
            )

        _approve()
        self.assertEqual(_active_parent_payment_count(), 1)
        self.assertEqual(_active_card_fee_count(), 1)

        _reopen("Primeira reabertura")
        _approve()

        self.assertEqual(_active_parent_payment_count(), 1)
        self.assertEqual(_active_card_fee_count(), 1)

        _reopen("Segunda reabertura")
        _approve()

        self.assertEqual(_active_parent_payment_count(), 1)
        self.assertEqual(_active_card_fee_count(), 1)

    def test_reopen_status_allows_cancelled_workorder(self) -> None:
        self.workorder.status = WorkOrderStatus.CANCELLED
        self.workorder.cancellation_reason = "Cliente desistiu do serviço."
        self.workorder.save(update_fields=["status", "cancellation_reason"])

        response = self.client.post(
            reverse("workorder:reopen", args=[self.workorder.pk]),
            data={"reopen_reason": "Cliente retomou o serviço."},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertEqual(self.workorder.status, WorkOrderStatus.DRAFT)
        self.assertEqual(self.workorder.reopen_reason, "Cliente retomou o serviço.")
        history_entry = WorkOrderHistory.objects.get(workorder=self.workorder, action=WorkOrderHistory.Action.REOPENED)
        self.assertEqual(history_entry.reason, "Cliente retomou o serviço.")

    def test_reopen_status_allows_rejected_workorder(self) -> None:
        self.workorder.status = WorkOrderStatus.REJECTED
        self.workorder.rejection_reason = "Cliente rejeitou o serviço."
        self.workorder.save(update_fields=["status", "rejection_reason"])

        response = self.client.post(
            reverse("workorder:reopen", args=[self.workorder.pk]),
            data={"reopen_reason": "Cliente aprovou nova análise."},
            HTTP_HX_REQUEST="true",
        )

        self.workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertEqual(self.workorder.status, WorkOrderStatus.DRAFT)
        self.assertEqual(self.workorder.reopen_reason, "Cliente aprovou nova análise.")
        history_entry = WorkOrderHistory.objects.get(workorder=self.workorder, action=WorkOrderHistory.Action.REOPENED)
        self.assertEqual(history_entry.reason, "Cliente aprovou nova análise.")

    def test_manager_can_reopen_approved_workorder(self) -> None:
        manager_user, workshop, _ = create_manager_user_with_workshop(suffix=48)
        customer = create_customer(workshop=workshop, suffix=248)
        vehicle = create_vehicle(workshop=workshop, customer=customer, suffix=248)
        budget = create_budget(workshop=workshop)
        budget.customer = customer
        budget.vehicle = vehicle
        budget.current_km = 12000
        budget.status = "approved"
        budget.save(update_fields=["customer", "vehicle", "current_km", "status"])
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED, delivered_at=timezone.now())

        self.client.force_login(manager_user)
        session = self.client.session
        session["active_workshop_id"] = workshop.pk
        session.save()

        response = self.client.post(
            reverse("workorder:reopen", args=[workorder.pk]),
            data={"reopen_reason": "Revisão autorizada pela gerência."},
            HTTP_HX_REQUEST="true",
        )

        workorder.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertEqual(workorder.status, WorkOrderStatus.DRAFT)

    def test_user_with_reopen_workorder_permission_can_reopen_approved_workorder(self) -> None:
        user = User.objects.create_user(username="workorder-perm-reopen", password="123", cpf="12345678123")
        account = Account.objects.create(name="Conta Permissao Reabertura", owner=user)
        user.account = account
        user.save(update_fields=["account"])

        workshop = Workshop.objects.create(
            account=account,
            name="Oficina Permissao Reabertura",
            cnpj="11.555.666/0001-48",
            phone="+5511966666666",
            address="Rua Permissao Reabertura, 48",
        )
        role = WorkshopRole.objects.create(account=account, name="Consultor")
        role.permissions.add(Permission.objects.get(content_type__app_label="workorder", codename="reopen_workorder"))
        WorkshopMember.objects.create(user=user, workshop=workshop, role=role, is_active=True)

        customer = create_customer(workshop=workshop, suffix=348)
        vehicle = create_vehicle(workshop=workshop, customer=customer, suffix=348)
        budget = create_budget(workshop=workshop)
        budget.customer = customer
        budget.vehicle = vehicle
        budget.current_km = 12000
        budget.status = "approved"
        budget.save(update_fields=["customer", "vehicle", "current_km", "status"])
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED, delivered_at=timezone.now())

        self.client.force_login(user)
        session = self.client.session
        session["active_workshop_id"] = workshop.pk
        session.save()

        response = self.client.post(
            reverse("workorder:reopen", args=[workorder.pk]),
            data={"reopen_reason": "Reabertura autorizada pela permissão da função."},
            HTTP_HX_REQUEST="true",
        )

        workorder.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("HX-Refresh"), "true")
        self.assertEqual(workorder.status, WorkOrderStatus.DRAFT)

    def test_payment_form_uses_pending_balance_after_discount(self) -> None:
        self.workorder.discount_value = Money("10.00", "BRL")
        self.workorder.save(update_fields=["discount_value"])

        payment_method = PaymentMethod.objects.create(workshop=self.workshop, description="Pix", installments_count=1)
        form = WorkOrderPaymentForm(
            data={
                "payment_method": str(payment_method.pk),
                "entry_amount_0": "95.00",
                "entry_amount_1": "BRL",
                "due_date": "2026-03-24",
                "discount_value_0": "10.00",
                "discount_value_1": "BRL",
                "discount_percentage": "0.10",
            },
            workorder=self.workorder,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("saldo pendente da O.S.", str(form.errors["entry_amount"][0]))
