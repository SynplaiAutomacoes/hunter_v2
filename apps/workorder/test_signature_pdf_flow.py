from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from apps.workorder.models import WorkOrderSignatureStatus
from apps.workorder.views import visualizar_pdf_workorder
from apps.core.domain.contracts.signature import SignatureServiceError


class WorkOrderSignaturePdfFlowTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_signed_pdf_is_default_only_when_workorder_is_approved(self) -> None:
        sent_workorder = SimpleNamespace(
            signature_request_status=WorkOrderSignatureStatus.SENT,
            signature_document_id="doc-1",
            signature_external_id="env-1",
        )
        approved_workorder = SimpleNamespace(
            signature_request_status=WorkOrderSignatureStatus.APPROVED,
            signature_document_id="doc-1",
            signature_external_id="env-1",
        )

        self.assertFalse(self._default_variant_for(sent_workorder) == "signed")
        self.assertTrue(self._default_variant_for(approved_workorder) == "signed")

    def _default_variant_for(self, workorder) -> str:
        return "signed" if workorder.signature_request_status == WorkOrderSignatureStatus.APPROVED and (workorder.signature_document_id or workorder.signature_external_id) else "base"

    def test_workorder_pdf_view_falls_back_to_base_pdf_when_signature_download_fails(self) -> None:
        request = self.factory.get("/workorder/visualizar-pdf/10?variant=signed")
        workorder = SimpleNamespace(
            id=10,
            pk=10,
            get_id=10,
            workshop=SimpleNamespace(),
            budget=SimpleNamespace(vehicle=None),
            signature_request_status=WorkOrderSignatureStatus.APPROVED,
            signature_document_id="doc-1",
            signature_external_id="env-1",
        )
        signature_service = Mock()
        signature_service.download_signed_document.side_effect = SignatureServiceError("signed unavailable")
        base_document = SimpleNamespace(content=b"%PDF-base", filename="ordem_servico_10_base.pdf")
        pdf_response = HttpResponse(b"%PDF-base", content_type="application/pdf")

        with (
            patch("apps.workorder.views.get_active_workshop_or_404", return_value=workorder.workshop),
            patch("apps.workorder.views.get_object_or_404", return_value=workorder),
            patch("apps.workorder.views.get_signature_service", return_value=signature_service),
            patch("apps.workorder.views.render_workorder_pdf_document", return_value=base_document) as render_document,
            patch("apps.workorder.views.build_pdf_http_response", return_value=pdf_response) as build_response,
        ):
            response = visualizar_pdf_workorder(request, pk=workorder.pk)

        self.assertIs(response, pdf_response)
        render_document.assert_called_once()
        build_response.assert_called_once_with(document=base_document, download=False)
