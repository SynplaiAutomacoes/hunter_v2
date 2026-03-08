from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlparse
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget, BudgetItem
from apps.budget.service import (
    BUDGET_SIGNATURE_DOCUMENT_ID_KEY,
    BUDGET_SIGNATURE_TOKEN_SALT,
    build_signature_file_url,
    build_signature_payload,
    build_signature_preview_url,
    send_budget_for_signature,
)
from apps.core.documents.contract import DocumentPayload, SignatureDeliveryResult
from apps.core.documents.signature import normalize_signature_phone_number, parse_document_signature_token
from apps.core.documents.services import SignatureDeliveryServiceError, get_signed_document_url
from apps.customer.models import Customer
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
        token = urlparse(url).path.rstrip("/").split("/")[-1]

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
        token = urlparse(url).path.rstrip("/").split("/")[-1]

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
