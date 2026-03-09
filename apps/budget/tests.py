from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlparse
from unittest.mock import patch

from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem, SignatureStatus
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
from apps.catalog.models.products import Product
from apps.core.documents.contract import DocumentPayload, SignatureDeliveryResult
from apps.core.documents.signature import normalize_signature_phone_number, parse_document_signature_token
from apps.core.documents.services import SignatureDeliveryServiceError, get_signed_document_url
from apps.customer.models import Customer
from apps.budget.views.pdf_views import signature_file, signature_preview, visualizar_pdf_assinatura
from apps.budget.views.workflow_views import trigger_signature_send_if_needed
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Budget {suffix}",
        cnpj=f"11.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


def create_budget(*, workshop: Workshop) -> Budget:
    budget = Budget(workshop=workshop, entry_date=timezone.now().date())
    budget.save()
    return budget


def create_customer(*, workshop: Workshop, suffix: int = 1, phone: str = "+5511999999999") -> Customer:
    return Customer.objects.create(
        workshop=workshop,
        name=f"Cliente {suffix}",
        cpf_or_cnpj=f"123.456.789-{suffix:02d}",
        email=f"cliente{suffix}@example.com",
        phone=phone,
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


def extract_token_from_url(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1]


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


class BudgetSignaturePersistenceTests(TestCase):
    def test_mark_signature_sent_persists_envelope_id(self) -> None:
        workshop = create_workshop(suffix=73)
        budget = create_budget(workshop=workshop)

        budget.mark_signature_sent("env-123")
        budget.refresh_from_db()

        self.assertEqual(budget.signature_external_id, "env-123")


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
        budget.signature_request_status = SignatureStatus.SENT
        budget.signature_external_id = "env-81"
        budget.save(update_fields=["signature_request_status", "signature_external_id"])

        active_workshop_mock.return_value = workshop
        download_signed_mock.return_value = b"%PDF-signed"

        request = self.factory.get("/", {"download": "1"})
        response = visualizar_pdf_assinatura(request, budget.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-signed")
        self.assertIn("attachment;", response["Content-Disposition"])

    @patch("apps.budget.views.pdf_views.get_active_workshop_or_404")
    @patch("apps.budget.views.pdf_views.render_budget_pdf_document")
    @patch("apps.budget.views.pdf_views.download_signed_document_content")
    def test_visualizar_pdf_assinatura_falls_back_to_base_pdf(self, download_signed_mock, render_document_mock, active_workshop_mock) -> None:
        workshop = create_workshop(suffix=82)
        budget = create_budget(workshop=workshop)
        budget.signature_request_status = SignatureStatus.SENT
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
        self.assertIn("headers", kwargs)
        self.assertEqual(kwargs["headers"]["x-account-id"], "acc-1")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret")

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
