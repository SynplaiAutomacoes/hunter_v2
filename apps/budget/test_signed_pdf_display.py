from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import RequestFactory, SimpleTestCase

from apps.budget.forms.presenters.step6_context import resolve_budget_pdf_modal_urls
from apps.budget.models import SignatureStatus
from apps.budget.service import can_use_signed_budget_pdf, should_default_to_signed_budget_pdf
from apps.budget.views.pdf_views import SIGNED_PDF_VARIANT, visualizar_pdf_assinatura
from apps.core.domain.contracts.signature import SignatureServiceError
from apps.workorder.models import WorkOrderSignatureStatus
from apps.workorder.views import _can_use_signed_workorder_pdf, _should_default_to_signed_workorder_pdf
from apps.workshops.services.synplaisign import WorkshopSynplaiSignError


class BudgetSignedPdfDefaultTests(SimpleTestCase):
    def test_should_default_to_signed_for_sent_status(self) -> None:
        budget = SimpleNamespace(
            signature_document_id="cmsdlv8mu001b225iskk7c0qj",
            signature_external_id="cmsdlv8mu001b225iskk7c0qj",
            signature_request_status=SignatureStatus.SENT,
        )
        self.assertTrue(can_use_signed_budget_pdf(budget=budget))
        self.assertTrue(should_default_to_signed_budget_pdf(budget=budget))

    def test_should_default_to_signed_for_approved_status(self) -> None:
        budget = SimpleNamespace(
            signature_document_id="env-1",
            signature_external_id="env-1",
            signature_request_status=SignatureStatus.APPROVED,
        )
        self.assertTrue(should_default_to_signed_budget_pdf(budget=budget))

    def test_should_not_default_without_signature_ids(self) -> None:
        budget = SimpleNamespace(
            signature_document_id="",
            signature_external_id="",
            signature_request_status=SignatureStatus.SENT,
        )
        self.assertFalse(can_use_signed_budget_pdf(budget=budget))
        self.assertFalse(should_default_to_signed_budget_pdf(budget=budget))


class WorkOrderSignedPdfDefaultTests(SimpleTestCase):
    def test_should_default_to_signed_for_sent_status(self) -> None:
        workorder = SimpleNamespace(
            signature_document_id="env-wo",
            signature_external_id="env-wo",
            signature_request_status=WorkOrderSignatureStatus.SENT,
        )
        self.assertTrue(_can_use_signed_workorder_pdf(workorder))
        self.assertTrue(_should_default_to_signed_workorder_pdf(workorder))


class BudgetPdfModalUrlTests(SimpleTestCase):
    def test_sent_toggle_opens_signed_variant_by_default(self) -> None:
        urls = resolve_budget_pdf_modal_urls(budget_id=849, can_toggle_signed_pdf=True)
        self.assertEqual(urls.initial_pdf_variant, "signed")
        self.assertIn("variant=signed", urls.default_pdf_url)
        self.assertIn("variant=signed", urls.default_pdf_download_url)
        self.assertEqual(urls.default_pdf_url, urls.signed_pdf_url)

    def test_without_toggle_opens_base_variant(self) -> None:
        urls = resolve_budget_pdf_modal_urls(budget_id=10, can_toggle_signed_pdf=False)
        self.assertEqual(urls.initial_pdf_variant, "base")
        self.assertIn("variant=base", urls.default_pdf_url)


class BudgetSignedPdfViewTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.workshop = SimpleNamespace(pk=19)
        self.budget = SimpleNamespace(
            id=849,
            pk=849,
            workshop=self.workshop,
            signature_document_id="cmsdlv8mu001b225iskk7c0qj",
            signature_external_id="cmsdlv8mu001b225iskk7c0qj",
            signature_request_status=SignatureStatus.SENT,
        )

    @patch("apps.budget.views.pdf_views.render_budget_pdf_document")
    @patch("apps.budget.views.pdf_views._get_budget_for_pdf")
    @patch("apps.budget.views.pdf_views.get_active_workshop_or_404")
    @patch("apps.core.infrastructure.services.signature_download.download_signed_pdf", return_value=b"%PDF-signed")
    @patch("apps.workshops.services.synplaisign.get_workshop_synplaisign_api_key", return_value="sk_live_x")
    def test_explicit_signed_variant_returns_synplaisign_bytes(
        self,
        _api_key_mock: Mock,
        download_mock: Mock,
        workshop_mock: Mock,
        budget_mock: Mock,
        render_base_mock: Mock,
    ) -> None:
        workshop_mock.return_value = self.workshop
        budget_mock.return_value = self.budget
        request = self.factory.get("/budget/visualizar-pdf-assinatura/849", {"variant": SIGNED_PDF_VARIANT})

        response = visualizar_pdf_assinatura(request, pk=849)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF-signed")
        download_mock.assert_called_once()
        render_base_mock.assert_not_called()

    @patch("apps.budget.views.pdf_views.render_budget_pdf_document")
    @patch("apps.budget.views.pdf_views._get_budget_for_pdf")
    @patch("apps.budget.views.pdf_views.get_active_workshop_or_404")
    @patch(
        "apps.core.infrastructure.services.signature_download.download_signed_pdf",
        side_effect=SignatureServiceError("falha synplaisign"),
    )
    @patch("apps.workshops.services.synplaisign.get_workshop_synplaisign_api_key", return_value="sk_live_x")
    def test_explicit_signed_variant_does_not_fallback_to_base_pdf(
        self,
        _api_key_mock: Mock,
        _download_mock: Mock,
        workshop_mock: Mock,
        budget_mock: Mock,
        render_base_mock: Mock,
    ) -> None:
        workshop_mock.return_value = self.workshop
        budget_mock.return_value = self.budget
        request = self.factory.get("/budget/visualizar-pdf-assinatura/849", {"variant": SIGNED_PDF_VARIANT})

        response = visualizar_pdf_assinatura(request, pk=849)

        self.assertEqual(response.status_code, 502)
        self.assertIn(b"falha synplaisign", response.content)
        render_base_mock.assert_not_called()

    @patch("apps.budget.views.pdf_views.render_budget_pdf_document")
    @patch("apps.budget.views.pdf_views._get_budget_for_pdf")
    @patch("apps.budget.views.pdf_views.get_active_workshop_or_404")
    @patch("apps.core.infrastructure.services.signature_download.download_signed_pdf")
    @patch(
        "apps.workshops.services.synplaisign.get_workshop_synplaisign_api_key",
        side_effect=WorkshopSynplaiSignError("Oficina sem API key"),
    )
    def test_explicit_signed_variant_propagates_missing_api_key(
        self,
        _api_key_mock: Mock,
        download_mock: Mock,
        workshop_mock: Mock,
        budget_mock: Mock,
        render_base_mock: Mock,
    ) -> None:
        workshop_mock.return_value = self.workshop
        budget_mock.return_value = self.budget
        request = self.factory.get("/budget/visualizar-pdf-assinatura/849", {"variant": SIGNED_PDF_VARIANT})

        response = visualizar_pdf_assinatura(request, pk=849)

        self.assertEqual(response.status_code, 502)
        self.assertIn(b"Oficina sem API key", response.content)
        download_mock.assert_not_called()
        render_base_mock.assert_not_called()
