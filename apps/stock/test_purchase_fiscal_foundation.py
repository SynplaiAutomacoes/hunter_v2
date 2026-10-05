from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from djmoney.money import Money

from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.finance.models.finance import FiscalDocument, FiscalDocumentOrigin, FiscalDocumentStatus
from apps.finance.models.payment_method import PaymentMethod
from apps.finance.services.nfe_returns import calculate_available_return_quantities
from apps.stock.forms import ImportStepSummaryForm
from apps.stock.models import StockImport, StockImportFiscalItem, StockMovement, StockProduct
from apps.stock.services.purchase_fiscal import PurchaseNfeValidationError, ensure_purchase_fiscal_foundation, parse_and_validate_purchase_nfe
from apps.workshops.models.workshops import Workshop


ACCESS_KEY = "35" + ("1" * 42)
SUPPLIER_CNPJ = "11222333000181"
WORKSHOP_CNPJ = "19131243000101"
User = get_user_model()


def build_purchase_nfe_xml(
    *,
    issuer_document: str = SUPPLIER_CNPJ,
    recipient_document: str = WORKSHOP_CNPJ,
    model: str = "55",
    protocol_status: str = "100",
    include_cancellation: bool = False,
) -> bytes:
    cancellation = ""
    if include_cancellation:
        cancellation = """
        <procEventoNFe>
          <evento><infEvento><tpEvento>110111</tpEvento></infEvento></evento>
          <retEvento><infEvento><cStat>135</cStat></infEvento></retEvento>
        </procEventoNFe>
        """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
      <NFe>
        <infNFe Id="NFe{ACCESS_KEY}">
          <ide>
            <cUF>35</cUF><mod>{model}</mod><serie>3</serie><nNF>987</nNF>
            <dhEmi>2026-08-02T10:00:00-03:00</dhEmi><tpNF>1</tpNF><finNFe>1</finNFe>
          </ide>
          <emit><CNPJ>{issuer_document}</CNPJ><xNome>Fornecedor Teste</xNome><IE>123456789</IE><enderEmit><xLgr>Rua do Fornecedor</xLgr><nro>100</nro><xBairro>Centro</xBairro><xMun>São Paulo</xMun><UF>SP</UF><CEP>01001000</CEP></enderEmit></emit>
          <dest><CNPJ>{recipient_document}</CNPJ><xNome>Oficina Teste</xNome></dest>
          <det nItem="1">
            <prod>
              <cProd>MOTOR-1</cProd><xProd>Motor</xProd><NCM>84099190</NCM><CFOP>5102</CFOP>
              <uCom>UN</uCom><qCom>2.0000</qCom><vUnCom>1500.5000</vUnCom><vProd>3001.00</vProd>
            </prod>
            <imposto><ICMS><ICMS00><orig>0</orig><CST>00</CST></ICMS00></ICMS></imposto>
          </det>
        </infNFe>
      </NFe>
      <protNFe><infProt><tpAmb>2</tpAmb><chNFe>{ACCESS_KEY}</chNFe><nProt>135260000000001</nProt><cStat>{protocol_status}</cStat></infProt></protNFe>
      {cancellation}
    </nfeProc>""".encode()


class PurchaseNfeValidationTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Teste",
            cnpj=WORKSHOP_CNPJ,
            phone="+5511999999999",
            address="Rua Teste, 123",
            uf="SP",
        )

    def test_validates_purchase_received_and_builds_normalized_snapshot(self) -> None:
        snapshot = parse_and_validate_purchase_nfe(workshop=self.workshop, xml_content=build_purchase_nfe_xml())

        self.assertEqual(snapshot["document"]["model"], "55")
        self.assertEqual(snapshot["document"]["operation_type"], "1")
        self.assertEqual(snapshot["document"]["protocol_status"], "100")
        self.assertEqual(snapshot["issuer"]["document"], SUPPLIER_CNPJ)
        self.assertEqual(snapshot["issuer"]["address"]["street"], "Rua do Fornecedor")
        self.assertEqual(snapshot["issuer"]["address"]["zip_code"], "01001000")
        self.assertEqual(snapshot["recipient"]["document"], WORKSHOP_CNPJ)
        self.assertEqual(
            snapshot["products"][0],
            {
                "sequence": 1,
                "product_code": "MOTOR-1",
                "description": "Motor",
                "quantity": "2.0000",
                "unit": "UN",
                "unit_value": "1500.5000",
                "total_value": "3001.00",
                "ncm": "84099190",
                "cfop": "5102",
                "taxes": {"ICMS": {"ICMS00": {"orig": "0", "CST": "00"}}},
            },
        )

    def test_rejects_documents_that_do_not_prove_a_valid_purchase(self) -> None:
        scenarios = {
            "wrong_model": build_purchase_nfe_xml(model="65"),
            "not_authorized": build_purchase_nfe_xml(protocol_status="110"),
            "cancelled": build_purchase_nfe_xml(include_cancellation=True),
            "issued_by_workshop": build_purchase_nfe_xml(issuer_document=WORKSHOP_CNPJ),
            "another_recipient": build_purchase_nfe_xml(recipient_document="99888777000166"),
        }
        for scenario, xml_content in scenarios.items():
            with self.subTest(scenario=scenario), self.assertRaises(PurchaseNfeValidationError):
                parse_and_validate_purchase_nfe(workshop=self.workshop, xml_content=xml_content)


class PurchaseFiscalFoundationTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Fundação",
            cnpj=WORKSHOP_CNPJ,
            phone="+5511988888888",
            address="Rua Fundação, 456",
            uf="SP",
        )
        group = CatalogGroup.objects.create(workshop=self.workshop, name="Motores")
        self.product = Product.objects.create(
            workshop=self.workshop,
            group=group,
            code="MOTOR-1",
            name="Motor",
            unit=Product.Unit.UND,
            cost_price=Money("1500.50", "BRL"),
            selling_price=Money("2000.00", "BRL"),
            ncm="84099190",
        )
        self.stock_product = StockProduct.objects.get(product=self.product)
        self.user = User.objects.create_user(username="purchase-fiscal", password="test", cpf="12345678901")
        self.snapshot = parse_and_validate_purchase_nfe(workshop=self.workshop, xml_content=build_purchase_nfe_xml())
        self.stock_import = StockImport.objects.create(
            workshop=self.workshop,
            nf_number="987",
            nf_key=ACCESS_KEY,
            supplier_name="Fornecedor Teste",
            supplier_cnpj=SUPPLIER_CNPJ,
            method=StockImport.ImportMethods.XML,
            items_data=[
                {
                    "nitem": 1,
                    "ref": "MOTOR-1",
                    "desc": "Motor",
                    "qtd": "2.0000",
                    "valor": "1500.5000",
                    "linked_product_id": self.product.pk,
                }
            ],
            fiscal_snapshot=self.snapshot,
            fiscal_validation_status=StockImport.FiscalValidationStatus.VALIDATED,
        )

    def test_materializes_external_document_and_normalized_items_idempotently(self) -> None:
        first_items = ensure_purchase_fiscal_foundation(stock_import=self.stock_import)
        second_items = ensure_purchase_fiscal_foundation(stock_import=self.stock_import)

        self.stock_import.refresh_from_db()
        fiscal_document = self.stock_import.fiscal_document
        self.assertIsNotNone(fiscal_document)
        assert fiscal_document is not None
        self.assertEqual(fiscal_document.origin, FiscalDocumentOrigin.EXTERNAL)
        self.assertEqual(fiscal_document.status, FiscalDocumentStatus.APPROVED)
        self.assertEqual(fiscal_document.access_key, ACCESS_KEY)
        self.assertEqual(fiscal_document.series, "3")
        self.assertEqual(fiscal_document.receipt, "135260000000001")
        self.assertEqual(self.stock_import.fiscal_issued_at, datetime.fromisoformat("2026-08-02T10:00:00-03:00"))
        self.assertEqual(FiscalDocument.objects.filter(access_key=ACCESS_KEY).count(), 1)
        self.assertEqual(calculate_available_return_quantities(original_document=fiscal_document), {1: Decimal("2.0000")})

        fiscal_item = StockImportFiscalItem.objects.get(stock_import=self.stock_import, sequence=1)
        self.assertEqual(first_items[1].pk, fiscal_item.pk)
        self.assertEqual(second_items[1].pk, fiscal_item.pk)
        self.assertEqual(fiscal_item.stock_product, self.stock_product)
        self.assertEqual(fiscal_item.quantity, Decimal("2.0000"))
        self.assertEqual(fiscal_item.unit_value, Decimal("1500.5000"))
        self.assertEqual(fiscal_item.tax_snapshot["ICMS"]["ICMS00"]["CST"], "00")

    def test_stock_entry_can_trace_purchase_document_and_fiscal_item(self) -> None:
        fiscal_item = ensure_purchase_fiscal_foundation(stock_import=self.stock_import)[1]

        movement = StockMovement.objects.create(
            workshop=self.workshop,
            stock_product=self.stock_product,
            source_import_item=fiscal_item,
            type=StockMovement.MovementType.ENTRY,
            quantity=2,
            status=StockMovement.MovementStatus.APPROVED,
        )

        self.assertEqual(movement.source_import_item.stock_import.fiscal_document.access_key, ACCESS_KEY)
        self.assertEqual(movement.source_import_item.sequence, 1)
        self.assertEqual(movement.entry_note_display, self.stock_import.nf_number_display)

    def test_stock_import_completion_links_created_entry_to_fiscal_item(self) -> None:
        payment_method = PaymentMethod.objects.create(
            workshop=self.workshop,
            description="BOLETO",
            payment_type=PaymentMethod.PaymentType.BOTH,
            is_active=True,
        )
        self.stock_import.user = self.user
        self.stock_import.payments_data = [
            {
                "id": 1,
                "method": payment_method.pk,
                "method_display": "BOLETO",
                "installments": 1,
                "first_amount": "3001.00",
                "total_paid": "3001.00",
                "payment_date": "2026-08-10",
            }
        ]
        self.stock_import.save(update_fields=["user", "payments_data"])
        form = ImportStepSummaryForm(
            data={},
            instance=self.stock_import,
            workshop=self.workshop,
            request=SimpleNamespace(user=self.user),
        )

        self.assertTrue(form.is_valid(), form.errors)
        completed_import = form.save()

        completed_import.refresh_from_db()
        movement = StockMovement.objects.get(source_import_item__stock_import=completed_import)
        self.stock_product.refresh_from_db()
        self.assertEqual(completed_import.status, StockImport.ImportStatus.COMPLETED)
        self.assertEqual(movement.source_import_item.sequence, 1)
        self.assertEqual(movement.source_import_item.stock_product, self.stock_product)
        self.assertEqual(self.stock_product.current_quantity, 2)
