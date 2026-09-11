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
from apps.finance.models.finance import FiscalDocument, FiscalDocumentOrigin, FiscalDocumentPurpose, FiscalDocumentStatus, NfeItem, NfeRequest, NfseItem, NfseRequest
from apps.finance.models.purchase_return import PurchaseReturnRequest, PurchaseReturnRequestStatus
from apps.stock.models import StockImport
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

    def _render_central(
        self,
        *,
        operation: str = "",
        operation_label: str = "",
        rows: list[dict[str, object]] | None = None,
        selected_fiscal_nfe: dict[str, object] | None = None,
    ) -> str:
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
                "issued_note_rows": rows or [],
                "issued_notes_total": len(rows or []),
                "issued_nfe_total": len(rows or []),
                "issued_nfse_total": 0,
                "download_xml_url": "/finance/notas-emitidas/download/xml/",
                "download_pdfs_url": "/finance/notas-emitidas/download/pdfs/",
                "report_pdf_url": "/finance/notas-emitidas/relatorio/pdf/",
                "report_excel_url": "/finance/notas-emitidas/relatorio/excel/",
                "fiscal_operation": operation,
                "fiscal_operation_label": operation_label,
                "fiscal_operation_continuation_label": {
                    "return": "a devolução",
                    "correction": "a Carta de Correção",
                    "complementary": "a Nota Complementar",
                    "adjustment": "a Nota de Ajuste",
                }.get(operation, ""),
                "selected_fiscal_nfe": selected_fiscal_nfe,
                "fiscal_selection_reset_url": "/finance/notas-emitidas/?tipo=nfe&operacao=return" if operation else "",
            }
        )
        return str(template.render(context))

    def test_central_distinguishes_consultation_from_new_emission(self) -> None:
        html = self._render_central()

        self.assertIn("Central de Notas", html)
        self.assertIn("Para criar um novo documento, use Emitir Nota.", html)
        self.assertIn(f'href="{reverse("finance:emission_create")}"', html)
        self.assertIn("Emitir Nota", html)
        self.assertIn('id="issued-documents-download-xml"', html)
        self.assertIn('id="issued-documents-download-pdfs"', html)

    def test_reference_selection_can_return_to_operation_gateway(self) -> None:
        html = self._render_central(operation="return", operation_label="Devolução")

        self.assertIn("Selecionar NF-e de referência", html)
        self.assertIn("Escolha a nota fiscal que será utilizada nesta operação.", html)
        self.assertIn("Operação atual: Devolução", html)
        self.assertIn(f'href="{reverse("finance:emission_create")}"', html)
        self.assertIn("Trocar operação", html)
        self.assertNotIn('id="issued-documents-download-xml"', html)
        self.assertNotIn('id="issued-documents-download-pdfs"', html)

    def test_reference_selection_uses_primary_action_and_explicit_confirmation(self) -> None:
        row: dict[str, object] = {
            "note_type": "nfe",
            "note_type_label": "Nota Fiscal de Produto",
            "note_type_badge_class": "badge-info",
            "request_id": 42,
            "selection_key": "nfe:42",
            "number": "1234",
            "reference": "Série 1",
            "workorder_id": "Manual",
            "customer_name": "Cliente Teste",
            "created_at": None,
            "status_badge": {"class": "badge-success", "text": "Aprovado"},
            "available_documents": ["XML", "DANFE"],
            "selection_url": "/finance/notas-emitidas/?tipo=nfe&operacao=return&selected_nfe=42",
            "detail_url": "/finance/nfe/42/?origin=issued_documents&tipo=nfe&operacao=return",
            "action_label": "Selecionar esta NF-e",
        }

        html = self._render_central(
            operation="return",
            operation_label="Devolução",
            rows=[row],
            selected_fiscal_nfe=row,
        )

        self.assertIn("✓ NF-e 1234 selecionada com sucesso", html)
        self.assertIn("A NF-e 1234 foi selecionada. Clique em continuar para prosseguir com a devolução.", html)
        self.assertIn("Continuar com NF-e 1234", html)
        self.assertIn("✓ NF-e selecionada", html)
        self.assertIn('aria-selected="true"', html)
        self.assertIn('aria-current="true"', html)
        self.assertIn('<tr class="!bg-success/10" aria-selected="true">', html)
        self.assertNotIn('<tr class="bg-success/15 ring-2 ring-inset ring-success/60"', html)
        self.assertNotIn(">Selecionar esta NF-e</a>", html)
        self.assertNotIn('name="note_selection"', html)
        self.assertNotIn(">Documentos</th>", html)

    def test_reference_selection_keeps_unselected_rows_available(self) -> None:
        selected_row: dict[str, object] = {
            "note_type": "nfe",
            "request_id": 42,
            "number": "1234",
            "customer_name": "Cliente Selecionado",
            "created_at": None,
            "detail_url": "/finance/nfe/42/",
            "selection_url": "/finance/notas-emitidas/?operacao=return&selected_nfe=42",
            "action_label": "Selecionar esta NF-e",
        }
        available_row: dict[str, object] = {
            **selected_row,
            "request_id": 43,
            "number": "1235",
            "customer_name": "Outro Cliente",
            "selection_url": "/finance/notas-emitidas/?operacao=return&selected_nfe=43",
        }

        html = self._render_central(
            operation="return",
            operation_label="Devolução",
            rows=[selected_row, available_row],
            selected_fiscal_nfe=selected_row,
        )

        self.assertEqual(html.count("✓ NF-e selecionada"), 1)
        self.assertEqual(html.count("Selecionar esta NF-e"), 1)
        self.assertIn('selected_nfe=43', html)

    def test_selected_state_is_consistent_for_all_reference_operations(self) -> None:
        row: dict[str, object] = {
            "note_type": "nfe",
            "request_id": 42,
            "number": "1234",
            "customer_name": "Cliente Teste",
            "created_at": None,
            "detail_url": "/finance/nfe/42/",
            "selection_url": "/finance/notas-emitidas/?selected_nfe=42",
            "action_label": "Selecionar esta NF-e",
        }
        operations = {
            "return": ("Devolução", "a devolução"),
            "correction": ("Carta de Correção", "a Carta de Correção"),
            "complementary": ("Nota Complementar", "a Nota Complementar"),
            "adjustment": ("Nota de Ajuste", "a Nota de Ajuste"),
        }

        for operation, (label, continuation_label) in operations.items():
            with self.subTest(operation=operation):
                html = self._render_central(operation=operation, operation_label=label, rows=[row], selected_fiscal_nfe=row)

                self.assertIn(label, html)
                self.assertIn("✓ NF-e selecionada", html)
                self.assertIn("Continuar com NF-e 1234", html)
                self.assertIn(f"Clique em continuar para prosseguir com {continuation_label}.", html)


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

    def test_list_includes_transmitted_purchase_return_with_its_documents(self) -> None:
        original_document = FiscalDocument.objects.create(
            workshop=self.workshop,
            origin=FiscalDocumentOrigin.EXTERNAL,
            purpose=FiscalDocumentPurpose.NORMAL,
            status=FiscalDocumentStatus.APPROVED,
            access_key="35" + ("1" * 42),
        )
        stock_import = StockImport.objects.create(
            workshop=self.workshop,
            nf_key="35" + ("1" * 42),
            supplier_name="Fornecedor da devolução",
            fiscal_document=original_document,
        )
        return_document = FiscalDocument.objects.create(
            workshop=self.workshop,
            origin=FiscalDocumentOrigin.DERIVED,
            purpose=FiscalDocumentPurpose.RETURN,
            status=FiscalDocumentStatus.APPROVED,
            number="456",
            series="2",
            xml_url="https://example.com/return.xml",
            danfe_url="https://example.com/return.pdf",
        )
        purchase_return = PurchaseReturnRequest.objects.create(
            workshop=self.workshop,
            source_stock_import=stock_import,
            original_document=original_document,
            fiscal_document=return_document,
            status=PurchaseReturnRequestStatus.AUTHORIZED,
        )
        view = IssuedDocumentsListView()
        view.workshop = self.workshop
        view.request = self.factory.get("/finance/notas-emitidas/")

        context = view.get_context_data()
        row = next(row for row in context["issued_note_rows"] if row["selection_key"] == f"purchase_return:{purchase_return.pk}")

        self.assertEqual(row["note_type_label"], "Nota de Devolução")
        self.assertEqual(row["number"], "456")
        self.assertTrue(row["has_xml"])
        self.assertTrue(row["has_pdf"])
        self.assertIn(reverse("finance:purchase_return_workflow", args=[purchase_return.pk]), row["detail_url"])

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
        self.assertEqual(row["action_label"], "Selecionar esta NF-e")
        self.assertIn(f"selected_nfe={nfe_request.pk}", row["selection_url"])
        self.assertIn("origin=issued_documents", row["detail_url"])
        self.assertIn("operacao=return", row["detail_url"])

    def test_fiscal_selection_mode_is_restricted_to_nfe_and_confirms_selection(self) -> None:
        nfe_request = self._create_nfe_with_xml(
            workshop=self.workshop,
            workorder=self.workorder,
            number="303",
            xml_url="https://example.com/selected-reference.xml",
        )
        self._create_nfse_with_xml(
            workshop=self.workshop,
            workorder=self.workorder,
            number="304",
            xml_url="https://example.com/not-a-reference.xml",
        )
        view = IssuedDocumentsListView()
        view.workshop = self.workshop
        view.request = self.factory.get(
            "/finance/notas-emitidas/",
            {"tipo": "all", "operacao": "return", "selected_nfe": str(nfe_request.pk)},
        )

        context = view.get_context_data()

        self.assertEqual(context["filter_state"]["selected_note_type"], "nfe")
        self.assertEqual(context["issued_nfse_total"], 0)
        self.assertTrue(all(row["note_type"] == "nfe" for row in context["issued_note_rows"]))
        self.assertEqual(context["selected_fiscal_nfe"]["request_id"], nfe_request.pk)
        self.assertIn("operacao=return", context["selected_fiscal_nfe"]["detail_url"])
        self.assertNotIn("selected_nfe", context["fiscal_selection_reset_url"])


class IssuedDocumentsStandaloneRowTests(SimpleTestCase):
    def test_build_nfe_row_supports_missing_workorder(self) -> None:
        view = IssuedDocumentsListView()
        request_obj = SimpleNamespace(
            pk=99,
            workorder_id=None,
            workorder=None,
            number_display_listing="123",
            reserved_series=1,
            criado_em=None,
            customer_name="Destinatario Avulso",
            nfe_request_status_badge={"class": "badge-success", "text": "Aprovado"},
        )
        with (
            patch.object(IssuedDocumentsListView, "_get_latest_prefetched_item", return_value=None),
            patch.object(IssuedDocumentsListView, "_build_available_document_labels", return_value=[]),
            patch.object(IssuedDocumentsListView, "_item_has_document_group", return_value=False),
            patch.object(IssuedDocumentsListView, "_build_detail_url", return_value="/finance/nfe/99/"),
            patch.object(IssuedDocumentsListView, "_build_selection_url", return_value=""),
        ):
            row = view._build_nfe_row(
                request_obj,
                state={"fiscal_operation": "", "search_raw": "", "note_type": "nfe", "status": "", "date_from": "", "date_to": ""},
            )

        self.assertEqual(row["workorder_id"], "Avulsa")
