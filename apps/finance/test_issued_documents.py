from __future__ import annotations

import zipfile
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.template import Context
from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from apps.budget.models import BudgetType
from apps.collaborators.test_commissions import create_workorder, create_workshop
from apps.finance.models.finance import NfeItem, NfeRequest, NfseItem, NfseRequest
from apps.finance.views.issued_documents import (
    ARCHIVE_DOWNLOAD_MAX_WORKERS,
    IssuedDocumentsArchiveDownloadView,
    IssuedDocumentsListView,
)


class IssuedDocumentsArchiveConcurrencyTests(SimpleTestCase):
    def test_archive_download_max_workers_is_five(self) -> None:
        self.assertEqual(ARCHIVE_DOWNLOAD_MAX_WORKERS, 5)

    @patch("apps.finance.views.issued_documents.ThreadPoolExecutor")
    @patch("apps.finance.views.issued_documents.get_fiscal_service")
    def test_download_document_entries_caps_workers_at_five(
        self,
        get_fiscal_service_mock: MagicMock,
        thread_pool_executor_mock: MagicMock,
    ) -> None:
        downloaded = SimpleNamespace(content=b"doc")
        get_fiscal_service_mock.return_value.download_document.return_value = downloaded

        executor = MagicMock()
        executor.__enter__.return_value = executor
        executor.__exit__.return_value = False
        futures: list[MagicMock] = []

        def submit(*args, **kwargs):
            future = MagicMock()
            future.result.return_value = downloaded
            futures.append(future)
            return future

        executor.submit.side_effect = submit
        thread_pool_executor_mock.return_value = executor

        with patch("apps.finance.views.issued_documents.as_completed", side_effect=lambda pending: list(pending)):
            view = IssuedDocumentsArchiveDownloadView()
            view.workshop = SimpleNamespace(pk=1)
            entries = [{"archive_name": f"doc-{index}.xml", "url": f"https://example.com/{index}.xml"} for index in range(8)]

            result = view._download_document_entries(entries=entries)

        thread_pool_executor_mock.assert_called_once_with(max_workers=5)
        self.assertEqual(len(futures), 8)
        self.assertEqual(len(result), 8)


class IssuedDocumentsNavigationTemplateTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def _render_central(self, *, operation: str = "", operation_label: str = "") -> str:
        request = self.factory.get("/finance/notas-emitidas/")
        request.user = SimpleNamespace(is_authenticated=True)
        template = get_template("finance/issued_documents_list.html").template
        context = Context(
            {
                "request": request,
                "filter_state": {
                    "has_selected_period": False,
                    "selected_note_type": "nfe" if operation else "all",
                    "search_raw": "",
                    "start_raw": "",
                    "end_raw": "",
                },
                "note_type_choices": (("all", "Todas"), ("nfe", "Nota Fiscal de Produto")),
                "issued_note_rows": [],
                "issued_notes_total": 0,
                "issued_nfe_total": 0,
                "issued_nfse_total": 0,
                "download_xml_url": "/finance/notas-emitidas/download/xml/",
                "download_pdfs_url": "/finance/notas-emitidas/download/pdfs/",
                "fiscal_operation": operation,
                "fiscal_operation_label": operation_label,
            }
        )
        return template.render(context)

    def test_central_distinguishes_consultation_from_new_emission(self) -> None:
        html = self._render_central()

        self.assertIn("Central de Notas", html)
        self.assertIn("Para criar um novo documento, use Emitir Nota.", html)
        self.assertIn(f'href="{reverse("finance:emission_create")}"', html)
        self.assertIn("Emitir Nota", html)

    def test_reference_selection_can_return_to_operation_gateway(self) -> None:
        html = self._render_central(operation="return", operation_label="Devolução")

        self.assertIn("Selecionar NF-e para Devolução", html)
        self.assertIn(f'href="{reverse("finance:emission_create")}"', html)
        self.assertIn("Trocar operação", html)


class IssuedDocumentsArchiveDownloadViewTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.workshop = create_workshop(suffix=41)
        self.other_workshop = create_workshop(suffix=42)
        self.workorder = create_workorder(workshop=self.workshop, budget_type=BudgetType.SALE)
        self.other_workorder = create_workorder(workshop=self.other_workshop, budget_type=BudgetType.SALE)

    def _create_nfe_with_xml(self, *, workshop, workorder, number: str, xml_url: str) -> NfeRequest:
        nfe_request = NfeRequest.objects.create(workshop=workshop, workorder=workorder, reserved_number=int(number))
        NfeItem.objects.create(
            workshop=workshop,
            workorder=workorder,
            request=nfe_request,
            uuid=uuid4(),
            number=number,
            access_key=f"KEY{number}",
            xml_url=xml_url,
            danfe_url=f"https://example.com/{number}.pdf",
        )
        return nfe_request

    def _create_nfse_with_xml(self, *, workshop, workorder, number: str, xml_url: str) -> NfseRequest:
        nfse_request = NfseRequest.objects.create(workshop=workshop, workorder=workorder, reserved_rps_number=int(number))
        NfseItem.objects.create(
            workshop=workshop,
            workorder=workorder,
            request=nfse_request,
            uuid=uuid4(),
            number=number,
            rps_number=number,
            xml_url=xml_url,
            pdf_nfse_url=f"https://example.com/nfse-{number}.pdf",
        )
        return nfse_request

    def test_post_without_selected_ids_returns_400(self) -> None:
        view = IssuedDocumentsArchiveDownloadView()
        view.workshop = self.workshop
        request = self.factory.post("/finance/notas-emitidas/download/xml/")
        view.request = request

        response = view.post(request, document_group="xml")

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Selecione ao menos uma nota", response.content)

    @patch("apps.finance.views.issued_documents.get_fiscal_service")
    def test_post_downloads_only_selected_notes(self, get_fiscal_service_mock: MagicMock) -> None:
        selected = self._create_nfe_with_xml(
            workshop=self.workshop,
            workorder=self.workorder,
            number="100",
            xml_url="https://example.com/selected.xml",
        )
        self._create_nfe_with_xml(
            workshop=self.workshop,
            workorder=self.workorder,
            number="101",
            xml_url="https://example.com/ignored.xml",
        )

        get_fiscal_service_mock.return_value.download_document.return_value = SimpleNamespace(content=b"<xml>selected</xml>")

        view = IssuedDocumentsArchiveDownloadView()
        view.workshop = self.workshop
        request = self.factory.post(
            "/finance/notas-emitidas/download/xml/",
            {"nfe_ids": [str(selected.pk)], "tipo": "nfe"},
        )
        view.request = request

        response = view.post(request, document_group="xml")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        get_fiscal_service_mock.return_value.download_document.assert_called_once_with(
            workshop=self.workshop,
            url="https://example.com/selected.xml",
        )

        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), 1)
            self.assertTrue(names[0].endswith(".xml"))
            self.assertEqual(archive.read(names[0]), b"<xml>selected</xml>")

    @patch("apps.finance.views.issued_documents.get_fiscal_service")
    def test_post_ignores_ids_from_other_workshop(self, get_fiscal_service_mock: MagicMock) -> None:
        foreign = self._create_nfe_with_xml(
            workshop=self.other_workshop,
            workorder=self.other_workorder,
            number="200",
            xml_url="https://example.com/foreign.xml",
        )

        view = IssuedDocumentsArchiveDownloadView()
        view.workshop = self.workshop
        request = self.factory.post(
            "/finance/notas-emitidas/download/xml/",
            {"nfe_ids": [str(foreign.pk)]},
        )
        view.request = request

        response = view.post(request, document_group="xml")

        self.assertEqual(response.status_code, 404)
        get_fiscal_service_mock.return_value.download_document.assert_not_called()

    def test_list_rows_include_selection_flags(self) -> None:
        nfe_request = self._create_nfe_with_xml(
            workshop=self.workshop,
            workorder=self.workorder,
            number="300",
            xml_url="https://example.com/list.xml",
        )
        nfse_request = self._create_nfse_with_xml(
            workshop=self.workshop,
            workorder=self.workorder,
            number="301",
            xml_url="https://example.com/list-nfse.xml",
        )

        view = IssuedDocumentsListView()
        view.workshop = self.workshop
        view.request = self.factory.get("/finance/notas-emitidas/")

        context = view.get_context_data()
        rows_by_key = {row["selection_key"]: row for row in context["issued_note_rows"]}

        nfe_row = rows_by_key[f"nfe:{nfe_request.pk}"]
        nfse_row = rows_by_key[f"nfse:{nfse_request.pk}"]

        self.assertTrue(nfe_row["has_xml"])
        self.assertTrue(nfe_row["has_pdf"])
        self.assertTrue(nfe_row["is_selectable"])
        self.assertTrue(nfse_row["has_xml"])
        self.assertTrue(nfse_row["has_pdf"])
        self.assertIn("/finance/notas-emitidas/download/xml/", context["download_xml_url"])
        self.assertIn("/finance/notas-emitidas/download/pdfs/", context["download_pdfs_url"])

    def test_gateway_operation_is_preserved_when_selecting_reference_nfe(self) -> None:
        nfe_request = self._create_nfe_with_xml(
            workshop=self.workshop,
            workorder=self.workorder,
            number="302",
            xml_url="https://example.com/gateway.xml",
        )
        view = IssuedDocumentsListView()
        view.workshop = self.workshop
        view.request = self.factory.get("/finance/notas-emitidas/", {"tipo": "nfe", "operacao": "return"})

        context = view.get_context_data()
        row = next(row for row in context["issued_note_rows"] if row["request_id"] == nfe_request.pk)

        self.assertEqual(context["fiscal_operation"], "return")
        self.assertEqual(context["fiscal_operation_label"], "Devolução")
        self.assertEqual(row["action_label"], "Selecionar")
        self.assertIn("origin=issued_documents", row["detail_url"])
        self.assertIn("operacao=return", row["detail_url"])
