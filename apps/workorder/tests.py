from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlparse
from unittest.mock import patch

from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from djmoney.money import Money

from apps.budget.documents.provider import build_budget_pdf_render_request
from apps.budget.models import Budget, BudgetItem
from apps.catalog.models.kits import Kit, KitProduct, KitService
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.catalog.models.services import Service
from apps.core.documents.contract import DocumentPayload, SignatureDeliveryResult
from apps.core.documents.services import SignatureDeliveryServiceError
from apps.core.documents.signature import normalize_signature_phone_number, parse_document_signature_token
from apps.customer.models import Customer
from apps.stock.models import StockMovement, StockProduct
from apps.workorder.approval import approve_workorder_with_stock
from apps.workorder.documents.provider import build_workorder_pdf_render_request
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderSignatureStatus, WorkOrderStatus
from apps.workorder.service import (
    WORKORDER_SIGNATURE_DOCUMENT_ID_KEY,
    WORKORDER_SIGNATURE_TOKEN_SALT,
    build_signature_file_url,
    build_signature_payload,
    build_signature_preview_url,
    send_workorder_for_signature,
)
from apps.workorder.views import signature_file, signature_preview, visualizar_pdf_workorder
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina OS {suffix}",
        cnpj=f"11.333.444/0001-{suffix:02d}",
        phone="+5511988888888",
        address="Rua Teste OS, 123",
    )


def create_budget(*, workshop: Workshop) -> Budget:
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
    def test_mark_signature_sent_persists_envelope_id(self) -> None:
        workshop = create_workshop(suffix=86)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        workorder.mark_signature_sent("env-123")
        workorder.refresh_from_db()

        self.assertEqual(workorder.signature_external_id, "env-123")
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
        workorder.signature_request_status = WorkOrderSignatureStatus.SENT
        workorder.signature_external_id = "env-87"
        workorder.save(update_fields=["signature_request_status", "signature_external_id"])

        active_workshop_mock.return_value = workshop
        download_signed_mock.return_value = b"%PDF-signed"

        request = self.factory.get("/", {"download": "1"})
        response = visualizar_pdf_workorder(request, workorder.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-signed")
        self.assertIn("attachment;", response["Content-Disposition"])

    @patch("apps.workorder.views.get_active_workshop_or_404")
    @patch("apps.workorder.views.render_workorder_pdf_document")
    @patch("apps.workorder.views.download_signed_document_content")
    def test_visualizar_pdf_workorder_falls_back_to_base_pdf(self, download_signed_mock, render_document_mock, active_workshop_mock) -> None:
        workshop = create_workshop(suffix=88)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.signature_request_status = WorkOrderSignatureStatus.SENT
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
