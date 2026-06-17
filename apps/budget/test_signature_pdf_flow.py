from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from apps.budget.models import SignatureStatus
from apps.budget.service import can_use_signed_budget_pdf, should_default_to_signed_budget_pdf
from apps.budget.views.pdf_views import visualizar_pdf_assinatura
from apps.core.domain.contracts.signature import SignatureServiceError
from apps.core.infrastructure.services.signature import SignatureDeliveryServiceError
from apps.core.infrastructure.services.signature_supersign import SuperSignSignatureService
from apps.customer.views import _build_customer_budget_history_entry


class BudgetSignaturePdfFlowTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_signed_pdf_is_default_only_when_budget_is_approved(self) -> None:
        sent_budget = SimpleNamespace(
            signature_request_status=SignatureStatus.SENT,
            signature_document_id="doc-1",
            signature_external_id="env-1",
        )
        approved_budget = SimpleNamespace(
            signature_request_status=SignatureStatus.APPROVED,
            signature_document_id="doc-1",
            signature_external_id="env-1",
        )

        self.assertTrue(can_use_signed_budget_pdf(budget=sent_budget))
        self.assertFalse(should_default_to_signed_budget_pdf(budget=sent_budget))
        self.assertTrue(should_default_to_signed_budget_pdf(budget=approved_budget))

    def test_customer_history_uses_base_variant_until_signature_is_approved(self) -> None:
        budget = SimpleNamespace(
            pk=538,
            criado_em=None,
            vehicle=None,
            display_total_budget_value=None,
            budget_status_badge={},
            signature_request_status=SignatureStatus.SENT,
            signature_document_id="doc-1",
            signature_external_id="env-1",
        )

        entry = _build_customer_budget_history_entry(budget)

        self.assertTrue(entry["pdf_url"].endswith("?variant=base"))
        self.assertTrue(entry["pdf_download_url"].endswith("?variant=base&download=1"))

    def test_signed_pdf_view_falls_back_to_base_pdf_when_signature_download_fails(self) -> None:
        request = self.factory.get("/budget/visualizar-pdf-assinatura/538?variant=signed")
        budget = SimpleNamespace(
            id=538,
            pk=538,
            workshop=SimpleNamespace(),
            signature_request_status=SignatureStatus.APPROVED,
            signature_document_id="doc-1",
            signature_external_id="env-1",
        )
        signature_service = Mock()
        signature_service.download_signed_document.side_effect = SignatureServiceError("signed unavailable")
        base_document = SimpleNamespace(content=b"%PDF-base", filename="orcamento_538_base.pdf")
        pdf_response = HttpResponse(b"%PDF-base", content_type="application/pdf")

        with (
            patch("apps.budget.views.pdf_views.get_active_workshop_or_404", return_value=budget.workshop),
            patch("apps.budget.views.pdf_views.get_object_or_404", return_value=budget),
            patch("apps.budget.views.pdf_views.get_signature_service", return_value=signature_service),
            patch("apps.budget.views.pdf_views.render_budget_pdf_document", return_value=base_document) as render_document,
            patch("apps.budget.views.pdf_views.build_pdf_http_response", return_value=pdf_response) as build_response,
        ):
            response = visualizar_pdf_assinatura(request, pk=budget.pk)

        self.assertIs(response, pdf_response)
        render_document.assert_called_once()
        build_response.assert_called_once_with(document=base_document, download=False)

    def test_signature_service_normalizes_delivery_error_to_signature_service_error(self) -> None:
        service = SuperSignSignatureService()

        with patch(
            "apps.core.infrastructure.services.signature_supersign.download_signed_document_content",
            side_effect=SignatureDeliveryServiceError("signed unavailable"),
        ):
            with self.assertRaises(SignatureServiceError):
                service.download_signed_document(document_id="doc-1")
