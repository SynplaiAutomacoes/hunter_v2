from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from apps.finance.views.nfse import NfsePreviewPdfView


class NfsePreviewViewTests(SimpleTestCase):
    def test_watermarked_template_receives_dynamic_preview_data(self) -> None:
        preview_data = {"numero": "PRÉVIA", "prestador": {}, "tomador": {}}

        html = render_to_string("pdf/nf_html_com_marca_dagua.html", {"nfse_preview": preview_data})

        self.assertIn('id="nfse-preview-data"', html)
        self.assertIn('"numero": "PR\\u00c9VIA"', html)
        self.assertIn("SEM VALOR FISCAL", html)

    @patch("apps.finance.views.nfse._build_nfse_preview_data")
    @patch("apps.finance.views.nfse.render")
    @patch("apps.finance.views.nfse.get_object_or_404")
    def test_preview_renders_local_watermarked_template_without_fiscal_api(
        self,
        get_object_or_404_mock: Mock,
        render_mock: Mock,
        build_preview_data_mock: Mock,
    ) -> None:
        request = RequestFactory().get("/finance/nfse/1/previa/pdf/")
        nfse_request = Mock(pk=1)
        workshop = Mock(pk=10)
        get_object_or_404_mock.return_value = nfse_request
        build_preview_data_mock.return_value = {"numero": "PRÉVIA"}
        render_mock.return_value = HttpResponse("preview")

        view = NfsePreviewPdfView()
        view.workshop = workshop
        response = view.get(request, pk=1)

        render_mock.assert_called_once_with(
            request,
            "pdf/nf_html_com_marca_dagua.html",
            {"nfse_preview": {"numero": "PRÉVIA"}},
        )
        self.assertEqual(response["Cache-Control"], "no-store")
