from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from djmoney.money import Money

from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.core.infrastructure.services.webmania.webmania_documents import DownloadedWebmaniaDocument
from apps.core.infrastructure.services.webmania.webmania_webhooks import process_webhook_event, store_webhook_event
from apps.core.infrastructure.services.webmania.nfe_emission import NfeEmissionUncertainError
from apps.finance.models import FiscalDocument, FiscalDocumentStatus, FiscalEmissionAttempt, TransportRequestStatus, TransportStockStatus
from apps.finance.models.finance import FiscalDocumentLinkRole, FiscalDocumentOrigin
from apps.finance.nfe_transport import build_nfe_transport_snapshot
from apps.finance.services.transport_requests import (
    TransportRequestError,
    available_transport_quantities,
    confirm_transport_document_from_payload,
    finalize_transport_request,
    preview_transport,
    reconcile_transport_document,
    save_transport_data,
    save_transport_items,
    select_transport_source,
    transmit_transport,
)
from apps.finance.views.transport_request import TransportWorkflowView
from apps.stock.models import StockImport, StockImportFiscalItem, StockMovement, StockProduct
from apps.suppliers.models import Supplier
from apps.workshops.models.workshops import Workshop


ACCESS_KEY = "35" + ("6" * 42)
EMITTED_KEY = "35" + ("5" * 42)
User = get_user_model()


class TransportRequestWorkflowTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="transport-request", password="test", cpf="12345678901")
        self.workshop = Workshop.objects.create(name="Oficina Transporte", cnpj="19131243000101", phone="+5511999999999", address="Rua Teste, 1", uf="SP")
        self.supplier = Supplier.objects.create(
            workshop=self.workshop,
            cnpj="19131243000101",
            name="Fornecedor Destinatário",
            cep="01001-000",
            logradouro="Praça da Sé",
            numero=100,
            bairro="Sé",
            cidade="São Paulo",
            estado="SP",
        )
        group = CatalogGroup.objects.create(workshop=self.workshop, name="Produtos transportados")
        product = Product.objects.create(
            workshop=self.workshop,
            group=group,
            code="MOTOR-T",
            name="Motor transportado",
            unit=Product.Unit.UND,
            cost_price=Money("100.00", "BRL"),
            selling_price=Money("150.00", "BRL"),
            ncm="84099190",
        )
        self.stock_product = StockProduct.objects.get(product=product)
        self.stock_product.current_quantity = Decimal("10.0000")
        self.stock_product.save(update_fields=["current_quantity"])
        self.original_document = FiscalDocument.objects.create(
            workshop=self.workshop,
            origin=FiscalDocumentOrigin.EXTERNAL,
            status=FiscalDocumentStatus.APPROVED,
            access_key=ACCESS_KEY,
            number="321",
            series="1",
        )
        self.stock_import = StockImport.objects.create(
            workshop=self.workshop,
            user=self.user,
            nf_number="321",
            nf_key=ACCESS_KEY,
            supplier_name=self.supplier.name,
            supplier_cnpj=str(self.supplier.cnpj),
            fiscal_document=self.original_document,
            fiscal_snapshot={"document": {"cancelled": False}},
            fiscal_validation_status=StockImport.FiscalValidationStatus.VALIDATED,
            status=StockImport.ImportStatus.COMPLETED,
        )
        self.source_item = StockImportFiscalItem.objects.create(
            stock_import=self.stock_import,
            sequence=1,
            stock_product=self.stock_product,
            product_code="MOTOR-T",
            description="Motor transportado",
            quantity=Decimal("10.0000"),
            unit="UN",
            unit_value=Decimal("100.0000"),
            total_value=Decimal("1000.00"),
            ncm="84099190",
            cfop="1102",
            tax_snapshot={"orig": 0, "cest": "0100100", "icms": {"cst": "00"}},
        )

    def _ready_request(self, quantity: Decimal = Decimal("3.0000")):
        request = select_transport_source(workshop=self.workshop, stock_import_id=self.stock_import.pk, requested_by=self.user)
        save_transport_items(request=request, quantities={self.source_item.pk: quantity})
        snapshot = build_nfe_transport_snapshot(
            {
                "freight_mode": "3",
                "transport_person_type": "",
                "transport_vehicle_plate": "ABC1D23",
                "transport_vehicle_state": "SP",
                "transport_volume_quantity": 1,
                "transport_volume_species": "Caixa",
            }
        )
        save_transport_data(request=request, freight_mode=3, transport_snapshot=snapshot, additional_information="Mercadoria própria; NF-e de entrada referenciada.")
        return finalize_transport_request(
            request=request,
            operation_nature="Remessa para transporte",
            cfop="5949",
            tax_class="classe-transporte",
        )

    def test_selects_source_and_blocks_quantity_above_physical_stock(self) -> None:
        request = select_transport_source(workshop=self.workshop, stock_import_id=self.stock_import.pk, requested_by=self.user)

        self.assertEqual(request.supplier, self.supplier)
        self.assertEqual(available_transport_quantities(stock_import=self.stock_import)[self.source_item.pk], Decimal("10.0000"))
        with self.assertRaisesMessage(TransportRequestError, "excede o estoque disponível"):
            save_transport_items(request=request, quantities={self.source_item.pk: Decimal("10.0001")})

    def test_blocks_aggregate_quantity_when_two_fiscal_items_point_to_same_stock_product(self) -> None:
        second_source_item = StockImportFiscalItem.objects.create(
            stock_import=self.stock_import,
            sequence=2,
            stock_product=self.stock_product,
            product_code="MOTOR-T-2",
            description="Motor transportado - segundo item",
            quantity=Decimal("8"),
            unit="UN",
            unit_value=Decimal("100"),
            total_value=Decimal("800"),
            ncm="84099190",
        )
        request = select_transport_source(workshop=self.workshop, stock_import_id=self.stock_import.pk, requested_by=self.user)

        with self.assertRaisesMessage(TransportRequestError, "soma das quantidades"):
            save_transport_items(request=request, quantities={self.source_item.pk: Decimal("6"), second_source_item.pk: Decimal("6")})

    def test_ready_intention_reserves_source_and_physical_balance(self) -> None:
        self._ready_request(quantity=Decimal("3"))
        second_user = User.objects.create_user(username="transport-request-2", password="test", cpf="98765432100")
        second = select_transport_source(workshop=self.workshop, stock_import_id=self.stock_import.pk, requested_by=second_user)

        self.assertEqual(available_transport_quantities(stock_import=self.stock_import, exclude_request=second)[self.source_item.pk], Decimal("7.0000"))

    def test_five_step_workflow_renders_transport_data_without_creating_fiscal_document(self) -> None:
        request_instance = select_transport_source(workshop=self.workshop, stock_import_id=self.stock_import.pk, requested_by=self.user)
        save_transport_items(request=request_instance, quantities={self.source_item.pk: Decimal("1")})
        http_request = self.factory.get(f"{reverse('finance:transport_workflow', args=[request_instance.pk])}?step=3")
        http_request.user = self.user
        view = TransportWorkflowView()
        view.setup(http_request, pk=request_instance.pk)
        view.workshop = self.workshop

        response = view.get(http_request, pk=request_instance.pk)

        self.assertContains(response, "Nota de Transporte")
        self.assertContains(response, "Dados de transporte")
        self.assertContains(response, "Modalidade de frete")
        self.assertContains(response, 'class="grid grid-cols-1 gap-3 md:grid-cols-5"')
        self.assertContains(response, "grid-template-columns: repeat(5, minmax(0, 1fr)) !important")
        self.assertEqual(FiscalDocument.objects.count(), 1)
        self.assertFalse(FiscalEmissionAttempt.objects.exists())

    def test_preview_has_reference_transport_and_no_fiscal_or_stock_side_effects(self) -> None:
        request = self._ready_request()
        downloaded = DownloadedWebmaniaDocument(content=b"%PDF", content_type="application/pdf", content_disposition="")

        with patch("apps.finance.services.transport_requests.validate_normal_nfe_tax_class"), patch(
            "apps.finance.services.transport_requests.download_normal_nfe_preview_payload", return_value=downloaded
        ) as preview_mock:
            result = preview_transport(request_instance=request)

        payload = preview_mock.call_args.kwargs["payload"]
        self.assertEqual(result.content, b"%PDF")
        self.assertEqual(payload["nfe_referenciada"], [ACCESS_KEY])
        self.assertEqual(payload["pedido"]["modalidade_frete"], 3)
        self.assertEqual(payload["produtos"][0]["codigo_cfop"], "5949")
        self.assertEqual(payload["produtos"][0]["quantidade"], "3")
        self.assertFalse(FiscalEmissionAttempt.objects.exists())
        self.assertFalse(StockMovement.objects.exists())
        self.stock_product.refresh_from_db()
        self.assertEqual(self.stock_product.current_quantity, Decimal("10.0000"))

    def test_authorized_transmission_creates_derived_document_attempt_link_and_exact_stock_exit(self) -> None:
        request = self._ready_request()
        response_payload = {"modelo": "nfe", "status": "aprovado", "uuid": "12345678-1234-4234-8234-123456789099", "chave": EMITTED_KEY, "nfe": "999", "serie": "1"}

        with patch("apps.finance.services.transport_requests.validate_normal_nfe_tax_class"), patch(
            "apps.finance.services.transport_requests.send_normal_nfe_payload", return_value=response_payload
        ):
            transmitted = transmit_transport(request_instance=request)

        transmitted.refresh_from_db()
        self.assertEqual(transmitted.status, TransportRequestStatus.AUTHORIZED)
        self.assertEqual(transmitted.stock_status, TransportStockStatus.PROCESSED)
        self.assertEqual(transmitted.fiscal_document.origin, FiscalDocumentOrigin.DERIVED)
        self.assertEqual(transmitted.fiscal_document.links_from.get().role, FiscalDocumentLinkRole.TRANSPORTS)
        self.assertEqual(transmitted.fiscal_document.request_payload["nfe_referenciada"], [ACCESS_KEY])
        self.assertEqual(FiscalEmissionAttempt.objects.count(), 1)
        movement = StockMovement.objects.get()
        self.assertEqual(movement.reason, StockMovement.MovementReason.TRANSPORT)
        self.assertEqual(movement.quantity, Decimal("3.0000"))
        self.assertEqual(movement.source_import_item, self.source_item)
        self.assertEqual(movement.fiscal_document, transmitted.fiscal_document)
        self.stock_product.refresh_from_db()
        self.assertEqual(self.stock_product.current_quantity, Decimal("7.0000"))

        confirm_transport_document_from_payload(document=transmitted.fiscal_document, response_payload=response_payload)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.stock_product.refresh_from_db()
        self.assertEqual(self.stock_product.current_quantity, Decimal("7.0000"))

    def test_rejected_transmission_does_not_move_stock(self) -> None:
        request = self._ready_request()
        response_payload = {"modelo": "nfe", "status": "reprovado", "uuid": "12345678-1234-4234-8234-123456789098", "message": "Rejeitada"}

        with patch("apps.finance.services.transport_requests.validate_normal_nfe_tax_class"), patch(
            "apps.finance.services.transport_requests.send_normal_nfe_payload", return_value=response_payload
        ), self.assertRaises(TransportRequestError):
            transmit_transport(request_instance=request)

        self.assertFalse(StockMovement.objects.exists())
        self.stock_product.refresh_from_db()
        self.assertEqual(self.stock_product.current_quantity, Decimal("10.0000"))

    def test_transmission_revalidates_stock_before_creating_derived_document(self) -> None:
        request = self._ready_request(quantity=Decimal("3"))
        self.stock_product.current_quantity = Decimal("2")
        self.stock_product.save(update_fields=["current_quantity"])

        with self.assertRaisesMessage(TransportRequestError, "excede o estoque disponível"):
            transmit_transport(request_instance=request)

        request.refresh_from_db()
        self.assertIsNone(request.fiscal_document_id)
        self.assertFalse(FiscalEmissionAttempt.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_duplicate_webhook_and_later_cancellation_do_not_duplicate_or_reverse_stock(self) -> None:
        request = self._ready_request(quantity=Decimal("2"))
        approved = {"modelo": "nfe", "status": "aprovado", "uuid": "12345678-1234-4234-8234-123456789097", "chave": EMITTED_KEY}
        with patch("apps.finance.services.transport_requests.validate_normal_nfe_tax_class"), patch(
            "apps.finance.services.transport_requests.send_normal_nfe_payload", return_value=approved
        ):
            transmitted = transmit_transport(request_instance=request)

        duplicate_event = store_webhook_event(payload=approved)
        self.assertTrue(process_webhook_event(duplicate_event))
        self.assertEqual(StockMovement.objects.count(), 1)
        self.stock_product.refresh_from_db()
        self.assertEqual(self.stock_product.current_quantity, Decimal("8.0000"))

        canceled = {**approved, "status": "cancelado"}
        cancellation_event = store_webhook_event(payload=canceled)
        self.assertTrue(process_webhook_event(cancellation_event))
        transmitted.refresh_from_db()
        self.assertEqual(transmitted.status, TransportRequestStatus.CANCELED)
        self.assertEqual(transmitted.stock_status, TransportStockStatus.PROCESSED)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.stock_product.refresh_from_db()
        self.assertEqual(self.stock_product.current_quantity, Decimal("8.0000"))

    def test_webhook_recovers_uncertain_timeout_by_stable_transport_request_id(self) -> None:
        request = self._ready_request(quantity=Decimal("2"))
        with patch("apps.finance.services.transport_requests.validate_normal_nfe_tax_class"), patch(
            "apps.finance.services.transport_requests.send_normal_nfe_payload",
            side_effect=NfeEmissionUncertainError("Timeout ao emitir Nota de Transporte; estado remoto incerto."),
        ), self.assertRaises(TransportRequestError):
            transmit_transport(request_instance=request)

        request.refresh_from_db()
        self.assertEqual(request.status, TransportRequestStatus.UNCERTAIN)
        self.assertFalse(StockMovement.objects.exists())
        approved = {
            "ID": f"transport-{request.pk}",
            "modelo": "nfe",
            "status": "aprovado",
            "uuid": "12345678-1234-4234-8234-123456789096",
            "chave": EMITTED_KEY,
        }

        event = store_webhook_event(payload=approved)
        self.assertTrue(process_webhook_event(event))
        request.refresh_from_db()
        self.assertEqual(request.status, TransportRequestStatus.AUTHORIZED)
        self.assertEqual(request.stock_status, TransportStockStatus.PROCESSED)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_reconciliation_authorizes_processing_document_and_applies_stock_once(self) -> None:
        request = self._ready_request(quantity=Decimal("2"))
        processing = {"modelo": "nfe", "status": "processando", "uuid": "12345678-1234-4234-8234-123456789095"}
        with patch("apps.finance.services.transport_requests.validate_normal_nfe_tax_class"), patch(
            "apps.finance.services.transport_requests.send_normal_nfe_payload", return_value=processing
        ):
            transmitted = transmit_transport(request_instance=request)

        self.assertEqual(transmitted.status, TransportRequestStatus.PROCESSING)
        self.assertFalse(StockMovement.objects.exists())
        approved = {**processing, "status": "aprovado", "chave": EMITTED_KEY}
        with patch("apps.finance.services.transport_requests.consult_nfe_document", return_value=approved):
            reconcile_transport_document(document=transmitted.fiscal_document)

        transmitted.refresh_from_db()
        self.assertEqual(transmitted.status, TransportRequestStatus.AUTHORIZED)
        self.assertEqual(StockMovement.objects.count(), 1)
        with patch("apps.finance.services.transport_requests.consult_nfe_document", return_value=approved):
            reconcile_transport_document(document=transmitted.fiscal_document)
        self.assertEqual(StockMovement.objects.count(), 1)
