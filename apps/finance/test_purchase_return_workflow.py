from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from djmoney.money import Money

from apps.budget.models import Budget
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.finance.forms.purchase_return import PurchaseReturnFiscalForm, PurchaseReturnItemsForm
from apps.finance.models import FiscalDocument, FiscalDocumentStatus, FiscalEmissionAttempt, PurchaseReturnItemKind, PurchaseReturnRequest, PurchaseReturnRequestItem, PurchaseReturnRequestStatus, PurchaseReturnStockStatus
from apps.finance.models.finance import FiscalDocumentOrigin, FiscalDocumentPurpose, NfeItem, NfeRequest
from apps.finance.services.nfe_returns import NfeReturnError, confirm_nfe_return_document_from_payload
from apps.finance.services.purchase_returns import (
    PurchaseReturnError,
    available_purchase_return_quantities,
    finalize_purchase_return_request,
    build_purchase_return_product_lines,
    find_purchase_by_access_key,
    find_purchase_by_id,
    get_or_create_purchase_return_request,
    search_purchase_imports,
    save_purchase_return_fiscal_data,
    save_purchase_return_items,
    preview_purchase_return,
    sync_purchase_return_status,
    transmit_purchase_return,
)
from apps.finance.views.purchase_return import PurchaseReturnCreateView, PurchaseReturnTransmitView, PurchaseReturnWorkflowView
from apps.stock.models import StockImport, StockImportFiscalItem, StockMovement, StockProduct
from apps.workshops.models.workshops import Workshop
from apps.workorder.models import WorkOrder, WorkOrderStatus


ACCESS_KEY = "35" + ("7" * 42)
LEGACY_ACCESS_KEY = "35" + ("8" * 42)
User = get_user_model()


class PurchaseReturnWorkflowTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="purchase-return", password="test", cpf="12345678901")
        self.workshop = Workshop.objects.create(name="Oficina Devolução", cnpj="19131243000101", phone="+5511999999999", address="Rua Teste, 1", uf="SP")
        self.other_workshop = Workshop.objects.create(name="Outra Oficina", cnpj="11222333000181", phone="+5511988888888", address="Rua Teste, 2", uf="SP")
        group = CatalogGroup.objects.create(workshop=self.workshop, name="Peças da compra")
        motor_product = Product.objects.create(
            workshop=self.workshop,
            group=group,
            code="MOTOR",
            name="Motor",
            unit=Product.Unit.UND,
            cost_price=Money("1500.50", "BRL"),
            selling_price=Money("2000.00", "BRL"),
            ncm="84099190",
        )
        filter_product = Product.objects.create(
            workshop=self.workshop,
            group=group,
            code="FILTRO",
            name="Filtro",
            unit=Product.Unit.UND,
            cost_price=Money("20.00", "BRL"),
            selling_price=Money("35.00", "BRL"),
            ncm="84212300",
        )
        self.motor_stock = StockProduct.objects.get(product=motor_product)
        self.motor_stock.current_quantity = Decimal("2.0000")
        self.motor_stock.save(update_fields=["current_quantity"])
        self.filter_stock = StockProduct.objects.get(product=filter_product)
        self.filter_stock.current_quantity = Decimal("10.0000")
        self.filter_stock.save(update_fields=["current_quantity"])
        self.document = FiscalDocument.objects.create(
            workshop=self.workshop,
            origin=FiscalDocumentOrigin.EXTERNAL,
            status=FiscalDocumentStatus.APPROVED,
            access_key=ACCESS_KEY,
            number="987",
            series="3",
            request_payload={"products": [{"sequence": 1, "quantity": "2.0000"}, {"sequence": 2, "quantity": "10.0000"}]},
        )
        self.stock_import = StockImport.objects.create(
            workshop=self.workshop,
            user=self.user,
            nf_number="987",
            nf_key=ACCESS_KEY,
            supplier_name="Fornecedor Teste",
            supplier_cnpj="99888777000166",
            status=StockImport.ImportStatus.COMPLETED,
            fiscal_document=self.document,
            fiscal_snapshot={"document": {"issued_at": "2026-08-02T10:00:00-03:00", "cancelled": False}},
            fiscal_issued_at=timezone.make_aware(datetime(2026, 8, 2, 10, 0)),
            fiscal_validation_status=StockImport.FiscalValidationStatus.VALIDATED,
        )
        self.motor = StockImportFiscalItem.objects.create(
            stock_import=self.stock_import,
            sequence=1,
            product_code="MOTOR",
            description="Motor",
            quantity=Decimal("2"),
            unit="UN",
            unit_value=Decimal("1500.50"),
            total_value=Decimal("3001"),
            ncm="84099190",
            cfop="5102",
            tax_snapshot={"orig": "0", "cest": "0100100", "icms": {"cst": "00"}},
            stock_product=self.motor_stock,
        )
        self.filter = StockImportFiscalItem.objects.create(
            stock_import=self.stock_import,
            sequence=2,
            product_code="FILTRO",
            description="Filtro",
            quantity=Decimal("10"),
            unit="UN",
            unit_value=Decimal("20"),
            total_value=Decimal("200"),
            stock_product=self.filter_stock,
        )

    def test_finds_only_authorized_external_purchase_from_current_workshop(self) -> None:
        found = find_purchase_by_access_key(workshop=self.workshop, access_key=ACCESS_KEY)

        self.assertEqual(found, self.stock_import)
        with self.assertRaisesMessage(PurchaseReturnError, "Não encontramos uma NF-e de compra válida"):
            find_purchase_by_access_key(workshop=self.other_workshop, access_key=ACCESS_KEY)
        with self.assertRaisesMessage(PurchaseReturnError, "44 dígitos"):
            find_purchase_by_access_key(workshop=self.workshop, access_key="123")

    def test_selection_supports_partial_multiple_items_and_ignores_zero(self) -> None:
        return_request = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=self.user)
        available = available_purchase_return_quantities(stock_import=self.stock_import)
        form = PurchaseReturnItemsForm(
            {f"quantity_{self.motor.pk}": "1.2500", f"quantity_{self.filter.pk}": "0"},
            request_instance=return_request,
            available_quantities=available,
        )

        self.assertTrue(form.is_valid(), form.errors)
        save_purchase_return_items(request=return_request, quantities=form.quantities())
        self.assertEqual(return_request.items.count(), 1)
        self.assertEqual(return_request.items.get().quantity, Decimal("1.2500"))

    def test_searches_received_purchases_by_all_supported_filters(self) -> None:
        scenarios = (
            {"supplier": "fornecedor"},
            {"number": "987"},
            {"issued_from": datetime(2026, 8, 1).date(), "issued_until": datetime(2026, 8, 3).date()},
            {"product": "motor"},
            {"value_min": Decimal("3200"), "value_max": Decimal("3202")},
            {"access_key": ACCESS_KEY[-8:]},
        )
        for filters in scenarios:
            with self.subTest(filters=filters):
                self.assertEqual(list(search_purchase_imports(workshop=self.workshop, filters=filters)), [self.stock_import])

        self.assertFalse(search_purchase_imports(workshop=self.workshop, filters={"product": "inexistente"}).exists())
        self.assertFalse(search_purchase_imports(workshop=self.other_workshop, filters={}).exists())

    def test_search_excludes_generic_fiscal_documents_without_stock_import(self) -> None:
        FiscalDocument.objects.create(
            workshop=self.workshop,
            origin=FiscalDocumentOrigin.EXTERNAL,
            purpose=FiscalDocumentPurpose.NORMAL,
            status=FiscalDocumentStatus.APPROVED,
            access_key="35" + ("1" * 42),
            request_payload={"products": [{"sequence": 1, "quantity": "1.0000"}]},
        )

        self.assertEqual(list(search_purchase_imports(workshop=self.workshop, filters={})), [self.stock_import])
        with self.assertRaisesMessage(PurchaseReturnError, "Não encontramos uma NF-e de compra válida"):
            find_purchase_by_access_key(workshop=self.workshop, access_key="35" + ("1" * 42))

    def test_search_excludes_local_workorder_invoice_without_stock_import(self) -> None:
        budget = Budget.objects.create(workshop=self.workshop, number=7001, entry_date=timezone.localdate())
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder, tax_class="REFNFE")
        nfe_item = NfeItem.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            request=nfe_request,
            uuid=uuid4(),
            status="aprovado",
            access_key="35" + ("2" * 42),
            number="7001",
            series="1",
            raw_payload={"produtos": [{"sequencial": 1, "quantidade": "1.0000"}]},
        )
        FiscalDocument.objects.create(
            workshop=self.workshop,
            origin=FiscalDocumentOrigin.LOCAL,
            purpose=FiscalDocumentPurpose.NORMAL,
            status=FiscalDocumentStatus.APPROVED,
            access_key=nfe_item.access_key,
            legacy_nfe_item=nfe_item,
        )

        self.assertEqual(list(search_purchase_imports(workshop=self.workshop, filters={})), [self.stock_import])
        with self.assertRaisesMessage(PurchaseReturnError, "Não encontramos uma NF-e de compra válida"):
            find_purchase_by_access_key(workshop=self.workshop, access_key=nfe_item.access_key)

    def test_legacy_import_without_stock_link_is_not_eligible(self) -> None:
        stock_import = StockImport.objects.create(
            workshop=self.workshop,
            user=self.user,
            nf_number="655",
            nf_key="35" + ("3" * 42),
            supplier_name="Fornecedor Sem Estoque",
            supplier_cnpj="88777666000155",
            method=StockImport.ImportMethods.XML,
            status=StockImport.ImportStatus.COMPLETED,
            items_data=[{"nitem": 1, "ref": "SEM-ESTOQUE", "desc": "Item sem vínculo", "qtd": "1.0000", "valor": "10.00"}],
        )

        self.assertEqual(list(search_purchase_imports(workshop=self.workshop, filters={"number": "655"})), [])
        with self.assertRaisesMessage(PurchaseReturnError, "não está autorizada"):
            find_purchase_by_id(workshop=self.workshop, stock_import_id=stock_import.pk, requested_by=self.user)

    def test_search_includes_normalized_legacy_purchase_without_validation_flag_or_cancelled_key(self) -> None:
        self.stock_import.fiscal_snapshot = {"document": {"issued_at": "2026-08-02T10:00:00-03:00"}}
        self.stock_import.fiscal_validation_status = StockImport.FiscalValidationStatus.UNVALIDATED
        self.stock_import.save(update_fields=["fiscal_snapshot", "fiscal_validation_status"])

        self.assertEqual(list(search_purchase_imports(workshop=self.workshop, filters={})), [self.stock_import])
        self.assertEqual(find_purchase_by_access_key(workshop=self.workshop, access_key=ACCESS_KEY), self.stock_import)

    def test_search_excludes_purchase_explicitly_marked_as_cancelled(self) -> None:
        self.stock_import.fiscal_snapshot = {"document": {"cancelled": True}}
        self.stock_import.save(update_fields=["fiscal_snapshot"])

        self.assertFalse(search_purchase_imports(workshop=self.workshop, filters={}).exists())
        with self.assertRaisesMessage(PurchaseReturnError, "não está autorizada"):
            find_purchase_by_access_key(workshop=self.workshop, access_key=ACCESS_KEY)

    def test_lists_and_selects_legacy_purchase_materializing_foundation_on_demand(self) -> None:
        legacy_import = StockImport.objects.create(
            workshop=self.workshop,
            user=self.user,
            nf_number="654",
            nf_key=LEGACY_ACCESS_KEY,
            supplier_name="Fornecedor Histórico",
            supplier_cnpj="88777666000155",
            status=StockImport.ImportStatus.COMPLETED,
            items_data=[
                {
                    "nitem": 1,
                    "ref": "MOTOR",
                    "desc": "Motor histórico",
                    "qtd": "3.0000",
                    "valor": "1200.00",
                    "unidade": "UN",
                    "ncm": "84099190",
                    "cfop": "5102",
                    "linked_product_id": self.motor_stock.product_id,
                }
            ],
        )
        self.motor_stock.current_quantity = Decimal("5.0000")
        self.motor_stock.save(update_fields=["current_quantity"])

        list_request = self.factory.get(reverse("finance:purchase_return_create"))
        list_request.user = self.user
        list_view = PurchaseReturnCreateView()
        list_view.setup(list_request)
        list_view.workshop = self.workshop
        list_response = list_view.get(list_request)

        self.assertContains(list_response, "Fornecedor Teste")
        self.assertContains(list_response, "Fornecedor Histórico")
        self.assertContains(list_response, "654")
        self.assertContains(list_response, "R$ 3.600,00")
        self.assertIsNone(legacy_import.fiscal_document_id)
        for filters in (
            {"supplier": "histórico"},
            {"number": "654"},
            {"issued_from": timezone.localdate(), "issued_until": timezone.localdate()},
            {"product": "motor historico"},
            {"value_min": Decimal("3599"), "value_max": Decimal("3601")},
            {"access_key": LEGACY_ACCESS_KEY[-8:]},
        ):
            with self.subTest(legacy_filters=filters):
                self.assertEqual(list(search_purchase_imports(workshop=self.workshop, filters=filters)), [legacy_import])

        selection_request = self.factory.post(reverse("finance:purchase_return_create"), {"stock_import_id": legacy_import.pk})
        selection_request.user = self.user
        selection_view = PurchaseReturnCreateView()
        selection_view.setup(selection_request)
        selection_view.workshop = self.workshop
        response = selection_view.post(selection_request)

        legacy_import.refresh_from_db()
        return_request = PurchaseReturnRequest.objects.get(source_stock_import=legacy_import)
        self.assertRedirects(response, f"{reverse('finance:purchase_return_workflow', args=[return_request.pk])}?step=2", fetch_redirect_response=False)
        self.assertIsNotNone(legacy_import.fiscal_document_id)
        self.assertEqual(legacy_import.fiscal_document.origin, FiscalDocumentOrigin.EXTERNAL)
        self.assertEqual(legacy_import.fiscal_document.status, FiscalDocumentStatus.APPROVED)
        self.assertEqual(legacy_import.fiscal_document.complementary_type, "")
        legacy_item = legacy_import.fiscal_items.get()
        self.assertEqual(legacy_item.description, "Motor histórico")
        self.assertEqual(legacy_item.stock_product, self.motor_stock)
        find_purchase_by_access_key(workshop=self.workshop, access_key=LEGACY_ACCESS_KEY, requested_by=self.user)
        self.assertEqual(FiscalDocument.objects.filter(access_key=LEGACY_ACCESS_KEY).count(), 1)
        self.assertEqual(legacy_import.fiscal_items.count(), 1)
        self.assertEqual(available_purchase_return_quantities(stock_import=legacy_import), {1: Decimal("3.0000")})
        save_purchase_return_items(request=return_request, quantities={legacy_item.pk: Decimal("1.0000")})
        finalize_purchase_return_request(request=return_request)
        self.assertEqual(available_purchase_return_quantities(stock_import=legacy_import), {1: Decimal("2.0000")})
        self.motor_stock.refresh_from_db()
        self.assertEqual(self.motor_stock.current_quantity, Decimal("5.0000"))

    def test_ready_intention_reserves_balance_and_blocks_overflow(self) -> None:
        first = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=self.user)
        save_purchase_return_items(request=first, quantities={self.motor.pk: Decimal("1.5")})
        finalize_purchase_return_request(request=first)

        self.assertEqual(available_purchase_return_quantities(stock_import=self.stock_import)[1], Decimal("0.5000"))
        second_user = User.objects.create_user(username="purchase-return-2", password="test", cpf="98765432100")
        second = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=second_user)
        with self.assertRaisesMessage(PurchaseReturnError, "excede o saldo disponível"):
            save_purchase_return_items(request=second, quantities={self.motor.pk: Decimal("0.5001")})

    def test_workflow_persists_steps_renders_review_and_creates_only_intention(self) -> None:
        return_request = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=self.user)
        save_purchase_return_items(request=return_request, quantities={self.motor.pk: Decimal("1")})
        request = self.factory.get(f"/finance/emissao/devolucao-compra/{return_request.pk}/?step=3")
        request.user = self.user
        view = PurchaseReturnWorkflowView()
        view.setup(request, pk=return_request.pk)
        view.workshop = self.workshop

        response = view.get(request, pk=return_request.pk)

        self.assertContains(response, "Revisar Nota de Devolução")
        self.assertContains(response, "Dados fiscais da Nota de Devolução")
        self.assertContains(response, "Valores do pedido")
        self.assertContains(response, "Despesas acessórias")
        self.assertContains(response, "Transporte")
        self.assertContains(response, "Motor")
        self.assertContains(response, "R$ 1.500,50")
        self.assertContains(response, "w-10 h-10")

        minimal_form = PurchaseReturnFiscalForm({"operation_nature": "Devolução de mercadoria", "cfop": "5202"}, instance=return_request)
        self.assertTrue(minimal_form.is_valid(), minimal_form.errors)
        self.assertEqual(minimal_form.cleaned_data["freight_mode"], 9)

        finalized = finalize_purchase_return_request(request=return_request)
        self.assertEqual(finalized.status, PurchaseReturnRequestStatus.READY)
        self.assertIsNone(finalized.fiscal_document)
        self.assertEqual(FiscalDocument.objects.count(), 1)

    def test_review_persists_optional_order_fields_and_sends_them_on_emission(self) -> None:
        return_request = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=self.user)
        save_purchase_return_items(request=return_request, quantities={self.motor.pk: Decimal("1")})
        invalid_intermediary = PurchaseReturnFiscalForm(
            {"operation_nature": "Devolução de mercadoria", "cfop": "5202", "intermediary": "1"},
            instance=return_request,
        )
        self.assertFalse(invalid_intermediary.is_valid())
        self.assertIn("intermediary_cnpj", invalid_intermediary.errors)

        request = self.factory.post(
            f"/finance/emissao/devolucao-compra/{return_request.pk}/?step=3",
            {
                "operation_nature": "Devolução de compra",
                "cfop": "5202",
                "tax_class": "REF-DEV",
                "additional_information": "Devolução parcial ao fornecedor",
                "fisco_information": "Informação ao fisco",
                "volume": "2",
                "freight_mode": "1",
                "freight_amount": "35.50",
                "discount_amount": "10.00",
                "accessory_expenses": "4.25",
                "insurance_amount": "1.10",
                "presence": "1",
                "payment_method": "90",
                "transport_volume_quantity": "2",
                "transport_volume_species": "CAIXA",
            },
        )
        request.user = self.user
        view = PurchaseReturnWorkflowView()
        view.setup(request, pk=return_request.pk)
        view.workshop = self.workshop

        response = view.post(request, pk=return_request.pk)

        if response.status_code != 302:
            self.fail(response.content.decode("utf-8", errors="replace")[:4000])
        return_request.refresh_from_db()
        self.assertEqual(return_request.status, PurchaseReturnRequestStatus.READY)
        self.assertEqual(return_request.operation_nature, "Devolução de compra")
        self.assertEqual(return_request.freight_mode, 1)
        self.assertEqual(return_request.freight_amount, Decimal("35.50"))
        self.assertEqual(return_request.discount_amount, Decimal("10.00"))
        self.assertEqual(return_request.accessory_expenses, Decimal("4.25"))
        self.assertEqual(return_request.insurance_amount, Decimal("1.10"))
        self.assertEqual(return_request.volume, 2)
        self.assertEqual(return_request.payment_method, "90")
        self.assertEqual(return_request.transport_snapshot["volumes"]["volume"], 2)
        self.assertEqual(return_request.transport_snapshot["volumes"]["especie"].upper(), "CAIXA")

        emit_response = MagicMock()
        emit_response.headers = {"Content-Type": "application/json"}
        emit_response.raise_for_status.return_value = None
        emit_response.json.return_value = {
            "status": "aprovado",
            "modelo": "nfe",
            "uuid": str(uuid4()),
            "chave": "35" + ("6" * 42),
            "nfe": "4321",
            "serie": "1",
        }
        with patch("apps.finance.services.nfe_returns._build_headers", return_value={}), patch("apps.finance.services.nfe_returns.requests.post", return_value=emit_response) as post_mock:
            transmitted = transmit_purchase_return(request_instance=return_request)

        payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(transmitted.fiscal_document.request_payload["pedido"]["frete"], "35.50")
        self.assertEqual(payload["pedido"]["desconto"], "10.00")
        self.assertEqual(payload["pedido"]["despesas_acessorias"], "4.25")
        self.assertEqual(payload["pedido"]["modalidade_frete"], 1)
        self.assertEqual(payload["pedido"]["presenca"], 1)
        self.assertEqual(payload["pedido"]["forma_pagamento"], "90")
        self.assertEqual(payload["transporte"]["seguro"], "1.10")
        self.assertEqual(payload["transporte"]["volume"], 2)
        self.assertEqual(payload["transporte"]["especie"].upper(), "CAIXA")
        self.assertEqual(payload["volume"], "2")
        self.assertEqual(payload["informacoes_fisco"], "Informação ao fisco")

    def test_empty_optional_fiscal_fields_are_omitted_from_return_payload(self) -> None:
        return_request = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=self.user)
        save_purchase_return_items(request=return_request, quantities={self.motor.pk: Decimal("1")})
        save_purchase_return_fiscal_data(
            request=return_request,
            cleaned_data={"operation_nature": "Devolução de mercadoria", "cfop": "5202", "freight_mode": 9, "transport_snapshot": {}},
        )
        return_request = finalize_purchase_return_request(request=return_request)
        response = MagicMock()
        response.headers = {"Content-Type": "application/json"}
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "status": "aprovado",
            "modelo": "nfe",
            "uuid": str(uuid4()),
            "chave": "35" + ("5" * 42),
            "nfe": "4322",
            "serie": "1",
        }
        with patch("apps.finance.services.nfe_returns._build_headers", return_value={}), patch("apps.finance.services.nfe_returns.requests.post", return_value=response) as post_mock:
            transmit_purchase_return(request_instance=return_request)

        payload = post_mock.call_args.kwargs["json"]
        self.assertNotIn("pedido", payload)
        self.assertNotIn("transporte", payload)
        self.assertNotIn("volume", payload)
        self.assertNotIn("informacoes_fisco", payload)

    def test_adapter_preserves_selected_partial_item_snapshot(self) -> None:
        return_request = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=self.user)
        save_purchase_return_items(request=return_request, quantities={self.motor.pk: Decimal("1.25")})

        lines = build_purchase_return_product_lines(request=return_request)

        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].code, "MOTOR")
        self.assertEqual(lines[0].ncm, "84099190")
        self.assertEqual(lines[0].quantity, Decimal("1.25"))
        self.assertEqual(lines[0].base_total, Decimal("1875.625"))

    def test_manual_item_persists_only_fiscal_snapshot_without_product_or_stock_link(self) -> None:
        return_request = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=self.user)
        manual_item = {
            "description": "Produto avulso devolvido",
            "product_code": "AV-1",
            "ncm": "87089990",
            "unit": "UN",
            "quantity": Decimal("1"),
            "unit_value": Decimal("25.50"),
            "cfop": "5202",
            "origin": 0,
        }

        save_purchase_return_items(request=return_request, quantities={}, manual_items=[manual_item])

        saved_item = return_request.items.get()
        self.assertEqual(saved_item.kind, PurchaseReturnItemKind.MANUAL)
        self.assertIsNone(saved_item.source_item_id)
        self.assertEqual(saved_item.manual_snapshot["description"], "Produto avulso devolvido")
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(StockProduct.objects.count(), 2)
        self.assertEqual(StockMovement.objects.count(), 0)
        self.assertEqual(available_purchase_return_quantities(stock_import=self.stock_import)[1], Decimal("2.0000"))

    def test_preview_uses_original_key_and_selected_items_without_creating_attempt(self) -> None:
        return_request = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=self.user)
        save_purchase_return_items(request=return_request, quantities={self.motor.pk: Decimal("1.25")})
        return_request.cfop = "5202"
        return_request.save(update_fields=["cfop", "atualizado_em"])
        return_request = finalize_purchase_return_request(request=return_request)
        response = MagicMock()
        response.headers = {"Content-Type": "application/pdf"}
        response.content = b"%PDF-preview"
        response.raise_for_status.return_value = None

        with patch("apps.finance.services.nfe_returns._build_headers", return_value={}), patch("apps.finance.services.nfe_returns.requests.post", return_value=response) as post_mock:
            downloaded = preview_purchase_return(request_instance=return_request)

        payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(downloaded.content, b"%PDF-preview")
        self.assertEqual(payload["chave"], ACCESS_KEY)
        self.assertEqual(payload["produtos"], [1])
        self.assertEqual(payload["quantidade"], ["1.25"])
        self.assertTrue(payload["previa_danfe"])
        self.assertEqual(FiscalEmissionAttempt.objects.count(), 0)
        self.assertEqual(FiscalDocument.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 0)
        self.motor_stock.refresh_from_db()
        self.assertEqual(self.motor_stock.current_quantity, Decimal("2.0000"))

    def test_preview_reads_ibs_cbs_from_imported_xml_snapshot(self) -> None:
        self.document.environment = "1"
        self.document.save(update_fields=["environment", "atualizado_em"])
        self.stock_import.fiscal_snapshot = {
            "products": [
                {
                    "sequence": 1,
                    "quantity": "2",
                    "taxes": {"IBSCBS": {"CST": "000", "cClassTrib": "000001"}},
                }
            ]
        }
        self.stock_import.save(update_fields=["fiscal_snapshot", "atualizado_em"])
        return_request = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=self.user)
        save_purchase_return_items(request=return_request, quantities={self.motor.pk: Decimal("1")})
        return_request.cfop = "5202"
        return_request.save(update_fields=["cfop", "atualizado_em"])
        return_request = finalize_purchase_return_request(request=return_request)
        response = MagicMock()
        response.headers = {"Content-Type": "application/pdf"}
        response.content = b"%PDF-preview"
        response.raise_for_status.return_value = None

        with patch("apps.finance.services.nfe_returns._build_headers", return_value={}), patch("apps.finance.services.nfe_returns.requests.post", return_value=response) as post_mock:
            preview_purchase_return(request_instance=return_request)

        ibs_cbs = post_mock.call_args.kwargs["json"]["produtos"][0]["impostos"]["ibs_cbs"]
        self.assertEqual(ibs_cbs["situacao_tributaria"], "000")
        self.assertEqual(ibs_cbs["classificacao_tributaria"], "000001")

    def test_transmission_creates_one_derived_document_link_and_attempt_idempotently(self) -> None:
        return_request = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=self.user)
        save_purchase_return_items(request=return_request, quantities={self.motor.pk: Decimal("1.25")})
        return_request.cfop = "5202"
        return_request.save(update_fields=["cfop", "atualizado_em"])
        return_request = finalize_purchase_return_request(request=return_request)
        response = MagicMock()
        response.headers = {"Content-Type": "application/json"}
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "status": "aprovado",
            "modelo": "nfe",
            "uuid": str(uuid4()),
            "chave": "35" + ("8" * 42),
            "nfe": "1234",
            "serie": "1",
        }

        with patch("apps.finance.services.nfe_returns._build_headers", return_value={}), patch("apps.finance.services.nfe_returns.requests.post", return_value=response) as post_mock:
            transmitted = transmit_purchase_return(request_instance=return_request)
            transmitted = transmit_purchase_return(request_instance=transmitted)

        transmitted.refresh_from_db()
        self.assertEqual(transmitted.status, PurchaseReturnRequestStatus.AUTHORIZED)
        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(FiscalEmissionAttempt.objects.count(), 1)
        self.assertEqual(FiscalDocument.objects.count(), 2)
        self.assertEqual(transmitted.stock_status, PurchaseReturnStockStatus.PROCESSED)
        self.assertEqual(StockMovement.objects.count(), 1)
        movement = StockMovement.objects.get()
        self.assertEqual(movement.type, StockMovement.MovementType.EXIT)
        self.assertEqual(movement.reason, StockMovement.MovementReason.PURCHASE_RETURN)
        self.assertEqual(movement.quantity, Decimal("1.2500"))
        self.assertEqual(movement.purchase_return_item, transmitted.items.get())
        self.assertEqual(movement.source_import_item, self.motor)
        self.assertEqual(movement.fiscal_document, transmitted.fiscal_document)
        self.assertEqual(movement.source_import_item.stock_import.fiscal_document, self.document)
        self.motor_stock.refresh_from_db()
        self.assertEqual(self.motor_stock.current_quantity, Decimal("0.7500"))
        link = transmitted.fiscal_document.links_from.get()
        self.assertEqual(link.related_document, self.document)
        self.assertEqual(link.metadata["purchase_return_request_id"], transmitted.pk)
        self.assertEqual(link.metadata["items"][0]["sequence"], 1)
        self.assertEqual(link.metadata["items"][0]["quantity"], "1.2500")
        self.assertEqual(transmitted.fiscal_document.request_payload["chave"], ACCESS_KEY)
        self.assertEqual(transmitted.fiscal_document.request_payload["produtos"], [1])

    def test_authorized_manual_only_return_does_not_move_stock_or_create_persistent_product(self) -> None:
        return_request = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=self.user)
        save_purchase_return_items(
            request=return_request,
            quantities={},
            manual_items=[
                {
                    "description": "Produto avulso devolvido",
                    "product_code": "AV-1",
                    "ncm": "87089990",
                    "unit": "UN",
                    "quantity": Decimal("1"),
                    "unit_value": Decimal("25.50"),
                    "cfop": "5202",
                    "origin": 0,
                }
            ],
        )
        return_request.cfop = "5202"
        return_request.save(update_fields=["cfop", "atualizado_em"])
        return_request = finalize_purchase_return_request(request=return_request)
        response = MagicMock()
        response.headers = {"Content-Type": "application/json"}
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "status": "aprovado",
            "modelo": "nfe",
            "uuid": str(uuid4()),
            "chave": "35" + ("9" * 42),
            "nfe": "1235",
            "serie": "1",
        }

        with patch("apps.finance.services.nfe_returns._build_headers", return_value={}), patch("apps.finance.services.nfe_returns.requests.post", return_value=response):
            transmitted = transmit_purchase_return(request_instance=return_request)

        transmitted.refresh_from_db()
        self.assertEqual(transmitted.status, PurchaseReturnRequestStatus.AUTHORIZED)
        self.assertEqual(transmitted.stock_status, PurchaseReturnStockStatus.PROCESSED)
        self.assertEqual(StockMovement.objects.count(), 0)
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(StockProduct.objects.count(), 2)
        self.motor_stock.refresh_from_db()
        self.assertEqual(self.motor_stock.current_quantity, Decimal("2.0000"))
        payload = transmitted.fiscal_document.request_payload
        self.assertNotIn("produtos", payload)
        self.assertIn("produtos_avulsos", payload)
        self.assertEqual(available_purchase_return_quantities(stock_import=self.stock_import)[1], Decimal("2.0000"))

    def test_rejected_return_does_not_change_stock(self) -> None:
        return_request = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=self.user)
        save_purchase_return_items(request=return_request, quantities={self.motor.pk: Decimal("1")})
        return_request.cfop = "5202"
        return_request.save(update_fields=["cfop", "atualizado_em"])
        return_request = finalize_purchase_return_request(request=return_request)
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"status": "reprovado", "error": "Rejeição fiscal"}

        with patch("apps.finance.services.nfe_returns._build_headers", return_value={}), patch("apps.finance.services.nfe_returns.requests.post", return_value=response):
            with self.assertRaises(PurchaseReturnError):
                transmit_purchase_return(request_instance=return_request)

        return_request.refresh_from_db()
        self.motor_stock.refresh_from_db()
        self.assertEqual(return_request.status, PurchaseReturnRequestStatus.REJECTED)
        self.assertEqual(return_request.stock_status, PurchaseReturnStockStatus.WAITING_AUTHORIZATION)
        self.assertEqual(StockMovement.objects.count(), 0)
        self.assertEqual(self.motor_stock.current_quantity, Decimal("2.0000"))
        self.assertEqual(available_purchase_return_quantities(stock_import=self.stock_import)[1], Decimal("2.0000"))

    def test_draft_creation_failure_releases_reservation_for_new_review(self) -> None:
        return_request = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=self.user)
        save_purchase_return_items(request=return_request, quantities={self.motor.pk: Decimal("1")})
        return_request.cfop = "5202"
        return_request.save(update_fields=["cfop", "atualizado_em"])
        return_request = finalize_purchase_return_request(request=return_request)

        with patch("apps.finance.services.purchase_returns.create_nfe_return_draft", side_effect=NfeReturnError("Dados fiscais inválidos")):
            with self.assertRaisesRegex(PurchaseReturnError, "Dados fiscais inválidos"):
                transmit_purchase_return(request_instance=return_request)

        return_request.refresh_from_db()
        self.assertEqual(return_request.status, PurchaseReturnRequestStatus.DRAFT)
        self.assertEqual(return_request.current_step, 3)
        self.assertIsNone(return_request.ready_at)
        self.assertIsNone(return_request.fiscal_document_id)
        self.assertEqual(available_purchase_return_quantities(stock_import=self.stock_import)[1], Decimal("2.0000"))

    def test_htmx_transmit_redirect_does_not_swap_workflow_into_preview_modal(self) -> None:
        return_request = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=self.user)
        request = self.factory.post(
            reverse("finance:purchase_return_transmit", args=[return_request.pk]),
            HTTP_HX_REQUEST="true",
        )
        request.user = self.user
        request.htmx = True
        request.session = {}
        request._messages = FallbackStorage(request)
        view = PurchaseReturnTransmitView()
        view.setup(request)
        view.workshop = self.workshop

        with patch("apps.finance.views.purchase_return.transmit_purchase_return", side_effect=PurchaseReturnError("Credenciais ausentes")):
            response = view.post(request, pk=return_request.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Redirect"], f"{reverse('finance:purchase_return_workflow', args=[return_request.pk])}?step=4")

    def test_authorized_return_reports_stock_error_when_product_is_not_linked(self) -> None:
        self.motor.stock_product = None
        self.motor.save(update_fields=["stock_product", "atualizado_em"])
        return_request = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=self.user)
        save_purchase_return_items(request=return_request, quantities={self.motor.pk: Decimal("1")})
        return_request.cfop = "5202"
        return_request.save(update_fields=["cfop", "atualizado_em"])
        return_request = finalize_purchase_return_request(request=return_request)
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "status": "aprovado",
            "modelo": "nfe",
            "uuid": str(uuid4()),
            "chave": "35" + ("6" * 42),
        }
        with patch("apps.finance.services.nfe_returns._build_headers", return_value={}), patch("apps.finance.services.nfe_returns.requests.post", return_value=response):
            return_request = transmit_purchase_return(request_instance=return_request)

        self.assertEqual(return_request.status, PurchaseReturnRequestStatus.AUTHORIZED)
        self.assertEqual(return_request.stock_status, PurchaseReturnStockStatus.ERROR)
        self.assertIn("sem vínculo com estoque", return_request.stock_error)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_duplicate_webhook_and_reconciliation_do_not_duplicate_stock_exit(self) -> None:
        return_request = get_or_create_purchase_return_request(stock_import=self.stock_import, requested_by=self.user)
        save_purchase_return_items(request=return_request, quantities={self.motor.pk: Decimal("0.7500")})
        return_request.cfop = "5202"
        return_request.save(update_fields=["cfop", "atualizado_em"])
        return_request = finalize_purchase_return_request(request=return_request)
        response_payload = {
            "status": "aprovado",
            "modelo": "nfe",
            "uuid": str(uuid4()),
            "chave": "35" + ("9" * 42),
            "nfe": "4321",
            "serie": "1",
        }
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = response_payload
        with patch("apps.finance.services.nfe_returns._build_headers", return_value={}), patch("apps.finance.services.nfe_returns.requests.post", return_value=response):
            return_request = transmit_purchase_return(request_instance=return_request)

        confirm_nfe_return_document_from_payload(document=return_request.fiscal_document, response_payload=response_payload)
        confirm_nfe_return_document_from_payload(document=return_request.fiscal_document, response_payload=response_payload)
        sync_purchase_return_status(request_instance=return_request)

        self.assertEqual(StockMovement.objects.count(), 1)
        self.motor_stock.refresh_from_db()
        self.assertEqual(self.motor_stock.current_quantity, Decimal("1.2500"))

        return_request.fiscal_document.status = FiscalDocumentStatus.CANCELED
        return_request.fiscal_document.save(update_fields=["status", "atualizado_em"])
        return_request = sync_purchase_return_status(request_instance=return_request)
        self.motor_stock.refresh_from_db()
        self.assertEqual(return_request.status, PurchaseReturnRequestStatus.CANCELED)
        self.assertEqual(return_request.stock_status, PurchaseReturnStockStatus.PROCESSED)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(self.motor_stock.current_quantity, Decimal("1.2500"))

    def test_source_selection_creates_reusable_draft_and_redirects_to_products(self) -> None:
        self.stock_import.fiscal_snapshot = {"document": {"issued_at": "2026-08-02T10:00:00-03:00"}}
        self.stock_import.fiscal_validation_status = StockImport.FiscalValidationStatus.UNVALIDATED
        self.stock_import.save(update_fields=["fiscal_snapshot", "fiscal_validation_status"])
        request = self.factory.post(reverse("finance:purchase_return_create"), {"stock_import_id": self.stock_import.pk})
        request.user = self.user
        view = PurchaseReturnCreateView()
        view.setup(request)
        view.workshop = self.workshop

        response = view.post(request)

        return_request = PurchaseReturnRequest.objects.get()
        self.assertRedirects(response, f"{reverse('finance:purchase_return_workflow', args=[return_request.pk])}?step=2", fetch_redirect_response=False)
        self.assertEqual(return_request.original_document, self.document)
        self.assertEqual(return_request.current_step, 2)

    def test_source_list_does_not_require_access_key_and_shows_document_summary(self) -> None:
        self.stock_import.fiscal_snapshot = {"document": {"issued_at": "2026-08-02T10:00:00-03:00"}}
        self.stock_import.fiscal_validation_status = StockImport.FiscalValidationStatus.UNVALIDATED
        self.stock_import.save(update_fields=["fiscal_snapshot", "fiscal_validation_status"])
        request = self.factory.get(reverse("finance:purchase_return_create"), {"supplier": "Fornecedor"})
        request.user = self.user
        view = PurchaseReturnCreateView()
        view.setup(request)
        view.workshop = self.workshop

        response = view.get(request)

        self.assertContains(response, "Pesquisar NF-e recebidas")
        self.assertContains(response, "Nota de Devolução")
        self.assertNotContains(response, "Devolução ao fornecedor")
        self.assertContains(response, "Fornecedor Teste")
        self.assertContains(response, "987")
        self.assertContains(response, "3")
        self.assertContains(response, "R$ 3.201,00")
        self.assertContains(response, "2 itens")
        self.assertContains(response, 'name="access_key"', html=False)
        self.assertNotContains(response, "Digite os 44 dígitos da chave")

    def test_schema_repair_is_idempotent_on_current_purchase_return_tables(self) -> None:
        from importlib.util import module_from_spec, spec_from_file_location
        from pathlib import Path

        from django.apps import apps
        from django.db import connection

        migration_path = Path(apps.get_app_config("finance").path) / "migrations" / "0058_repair_purchase_return_item_columns.py"
        spec = spec_from_file_location("repair_purchase_return_item_columns", migration_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        with connection.schema_editor() as schema_editor:
            module.repair_purchase_return_schema(apps, schema_editor)

        item_fields = {field.column for field in PurchaseReturnRequestItem._meta.local_concrete_fields}
        self.assertIn("manual_snapshot", item_fields)
        self.assertIn("kind", item_fields)
