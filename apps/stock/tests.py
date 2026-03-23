from __future__ import annotations

import base64
import gzip
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Account, User
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.collaborators.models import WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.stock.forms import ImportSefazListForm
from apps.stock.models import SefazZipCache, StockImport, StockMovement, StockProduct, StockTransfer
from apps.stock.utils import NFParser
from apps.workshops.models.workshops import Workshop


class StockSefazTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina Teste",
            cnpj="11.222.333/0001-81",
            phone="+5511999999999",
            address="Rua Teste, 123",
            uf="SP",
            pfx_certificate=SimpleUploadedFile("teste.pfx", b"certificado-teste", content_type="application/x-pkcs12"),
            certificate_password="segredo",
        )

    @staticmethod
    def _build_access_key(*, nf_number: int) -> str:
        return f"3526031122233300018155001{nf_number:09d}1123456789"

    def _build_res_nfe_xml(self, *, nf_number: int = 123, include_number: bool = True) -> bytes:
        access_key = self._build_access_key(nf_number=nf_number)
        number_xml = f"<nNF>{nf_number}</nNF>" if include_number else ""
        return f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<resNFe xmlns=\"http://www.portalfiscal.inf.br/nfe\">
    <chNFe>{access_key}</chNFe>
    {number_xml}
    <xNome>Fornecedor Teste</xNome>
    <CNPJ>11222333000181</CNPJ>
    <vNF>123.45</vNF>
    <dhEmi>2026-03-20T10:00:00-03:00</dhEmi>
</resNFe>
""".encode()

    def _build_distribution_response(self, *, document_xml: bytes) -> bytes:
        encoded_doc = base64.b64encode(gzip.compress(document_xml)).decode()
        return f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<retDistDFeInt xmlns=\"http://www.portalfiscal.inf.br/nfe\">
    <cStat>138</cStat>
    <xMotivo>Documentos localizados</xMotivo>
    <ultNSU>000000000000001</ultNSU>
    <maxNSU>000000000000001</maxNSU>
    <loteDistDFeInt>
        <docZip NSU=\"000000000000001\" schema=\"resNFe_v1.01.xsd\">{encoded_doc}</docZip>
    </loteDistDFeInt>
</retDistDFeInt>
""".encode()

    def test_parse_res_nfe_reads_number_from_element(self) -> None:
        parsed = NFParser.parse_nfe_xml_to_dict(self.workshop, self._build_res_nfe_xml())

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["nf_number"], "123")
        self.assertEqual(parsed["nf_key"], self._build_access_key(nf_number=123))

    def test_parse_res_nfe_falls_back_to_number_from_access_key(self) -> None:
        parsed = NFParser.parse_nfe_xml_to_dict(self.workshop, self._build_res_nfe_xml(include_number=False))

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["nf_number"], "123")

    def test_update_sefaz_list_persists_number_in_cache(self) -> None:
        response_content = self._build_distribution_response(document_xml=self._build_res_nfe_xml(include_number=False))
        form = ImportSefazListForm(workshop=self.workshop)

        with patch("apps.stock.forms.ComunicacaoSefaz") as comunicacao_cls:
            comunicacao_cls.return_value.consulta_distribuicao.return_value = SimpleNamespace(content=response_content)

            success, _message = form.update_sefaz_list()

        self.assertTrue(success)
        cache = SefazZipCache.objects.get(workshop=self.workshop, key=self._build_access_key(nf_number=123))
        self.assertEqual(cache.nf_number, "123")
        self.assertEqual(cache.nf_number_display, "123")

    def test_stock_import_number_display_falls_back_to_access_key(self) -> None:
        stock_import = StockImport.objects.create(
            workshop=self.workshop,
            nf_key=self._build_access_key(nf_number=987),
        )

        self.assertEqual(stock_import.nf_number_display, "987")


def create_director_user_with_workshop(*, suffix: int = 1) -> tuple[User, Workshop]:
    user = User.objects.create_user(username=f"stock_director{suffix}", password="123", cpf=f"33344455{suffix:03d}")
    account = Account.objects.create(name=f"Conta Estoque {suffix}", owner=user)
    user.account = account
    user.is_account_owner = True
    user.save(update_fields=["account", "is_account_owner"])

    workshop = Workshop.objects.create(
        account=account,
        name=f"Oficina Estoque {suffix}",
        cnpj=f"31.222.444/0001-{suffix:02d}",
        phone="+5511988887777",
        address="Rua Estoque, 10",
        uf="SP",
    )

    director_role = get_or_create_director_role(account=account, with_all_permissions=True)
    WorkshopMember.objects.create(user=user, workshop=workshop, role=director_role, is_active=True)
    return user, workshop


class StockTransferFlowTests(TestCase):
    def setUp(self) -> None:
        self.user, self.destination_workshop = create_director_user_with_workshop(suffix=20)
        self.source_workshop = Workshop.objects.create(
            account=self.destination_workshop.account,
            name="Oficina Origem",
            cnpj="31.222.444/0001-21",
            phone="+5511988887766",
            address="Rua Origem, 20",
            uf="SP",
        )
        director_role = get_or_create_director_role(account=self.destination_workshop.account, with_all_permissions=True)
        WorkshopMember.objects.create(user=self.user, workshop=self.source_workshop, role=director_role, is_active=True)

        self.source_group = CatalogGroup.objects.create(workshop=self.source_workshop, name="Filtros")
        self.destination_group = CatalogGroup.objects.create(workshop=self.destination_workshop, name="Filtros")
        self.source_product = Product.objects.create(
            workshop=self.source_workshop,
            code="FLT-001",
            name="Filtro de Oleo",
            unit=Product.Unit.UND,
            group=self.source_group,
            cost_price="10.00",
            selling_price="15.00",
            origin_cst=Product.OriginCST.NACIONAL,
            purpose=Product.Purpose.RESALE,
        )
        self.destination_product = Product.objects.create(
            workshop=self.destination_workshop,
            code="FLT-DEST-001",
            name="Filtro de Oleo Destino",
            unit=Product.Unit.UND,
            group=self.destination_group,
            cost_price="11.00",
            selling_price="16.00",
            origin_cst=Product.OriginCST.NACIONAL,
            purpose=Product.Purpose.RESALE,
        )
        self.source_stock = StockProduct.objects.get(workshop=self.source_workshop, product=self.source_product)
        self.source_stock.current_quantity = 8
        self.source_stock.save(update_fields=["current_quantity"])
        self.destination_stock = StockProduct.objects.get(workshop=self.destination_workshop, product=self.destination_product)
        self.destination_stock.current_quantity = 2
        self.destination_stock.save(update_fields=["current_quantity"])

        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.destination_workshop.pk
        session.save()

    def test_transfer_workflow_moves_stock_between_workshops(self) -> None:
        response = self.client.post(reverse("stock:transfer") + "?step=1", {"source_workshop": self.source_workshop.pk, "destination_workshop": self.destination_workshop.pk})
        self.assertEqual(response.status_code, 302)

        transfer = StockTransfer.objects.get()
        transfer.items_data = [
            {
                "source_product_id": str(self.source_product.pk),
                "destination_product_id": str(self.destination_product.pk),
                "qtd": 3,
                "valor": "10.00",
            }
        ]
        transfer.current_step = 3
        transfer.save(update_fields=["items_data", "current_step"])

        response = self.client.post(reverse("stock:transfer_update", kwargs={"pk": transfer.pk}) + "?step=3", {})
        self.assertEqual(response.status_code, 302)

        transfer.refresh_from_db()
        self.source_stock.refresh_from_db()
        self.destination_stock.refresh_from_db()

        self.assertEqual(transfer.status, StockTransfer.TransferStatus.COMPLETED)
        self.assertEqual(self.source_stock.current_quantity, 5)
        self.assertEqual(self.destination_stock.current_quantity, 5)

        exit_movement = StockMovement.objects.get(workshop=self.source_workshop, stock_transfer=transfer, type=StockMovement.MovementType.EXIT)
        entry_movement = StockMovement.objects.get(workshop=self.destination_workshop, stock_transfer=transfer, type=StockMovement.MovementType.ENTRY)
        self.assertEqual(exit_movement.quantity, 3)
        self.assertEqual(entry_movement.quantity, 3)

    def test_transfer_summary_blocks_when_source_stock_is_insufficient(self) -> None:
        transfer = StockTransfer.objects.create(
            source_workshop=self.source_workshop,
            destination_workshop=self.destination_workshop,
            user=self.user,
            current_step=3,
            items_data=[
                {
                    "source_product_id": str(self.source_product.pk),
                    "destination_product_id": str(self.destination_product.pk),
                    "qtd": 99,
                    "valor": "10.00",
                }
            ],
        )

        response = self.client.post(reverse("stock:transfer_update", kwargs={"pk": transfer.pk}) + "?step=3", {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Saldo insuficiente")

        transfer.refresh_from_db()
        self.source_stock.refresh_from_db()
        self.destination_stock.refresh_from_db()
        self.assertEqual(transfer.status, StockTransfer.TransferStatus.DRAFT)
        self.assertEqual(self.source_stock.current_quantity, 8)
        self.assertEqual(self.destination_stock.current_quantity, 2)

    def test_create_destination_product_endpoint_clones_product_into_destination(self) -> None:
        transfer = StockTransfer.objects.create(
            source_workshop=self.source_workshop,
            destination_workshop=self.destination_workshop,
            user=self.user,
            current_step=2,
            items_data=[
                {
                    "source_product_id": str(self.source_product.pk),
                    "destination_product_id": None,
                    "qtd": 1,
                    "valor": "10.00",
                }
            ],
        )

        response = self.client.post(reverse("stock:create_transfer_destination_product") + f"?pk={transfer.pk}&item_idx=0")
        self.assertEqual(response.status_code, 204)

        transfer.refresh_from_db()
        destination_product_id = transfer.items_data[0]["destination_product_id"]
        self.assertIsNotNone(destination_product_id)

        created_product = Product.objects.get(pk=destination_product_id)
        self.assertEqual(created_product.workshop, self.destination_workshop)
        self.assertEqual(created_product.code, self.source_product.code)
        self.assertEqual(created_product.group.name, self.source_group.name)

    def test_stock_history_lists_imports_and_transfers(self) -> None:
        stock_import = StockImport.objects.create(
            workshop=self.destination_workshop,
            user=self.user,
            nf_key="0" * 44,
            nf_number="1234",
            supplier_name="Fornecedor XPTO",
            status=StockImport.ImportStatus.COMPLETED,
        )
        transfer = StockTransfer.objects.create(
            source_workshop=self.source_workshop,
            destination_workshop=self.destination_workshop,
            user=self.user,
            status=StockTransfer.TransferStatus.COMPLETED,
        )

        response = self.client.get(reverse("stock:stock_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1234")
        self.assertContains(response, "Fornecedor XPTO")
        self.assertContains(response, "TRANSFERENCIA")
        self.assertContains(response, f"{self.source_workshop.name} -&gt; {self.destination_workshop.name}")
        self.assertContains(response, reverse("stock:history_edit", kwargs={"record_type": "import", "pk": stock_import.pk}))
        self.assertContains(response, reverse("stock:history_edit", kwargs={"record_type": "transfer", "pk": transfer.pk}))
        self.assertContains(response, reverse("stock:stock_delete", args=[stock_import.pk]))
        self.assertEqual(response.content.decode("utf-8").count("btn-table-delete"), 2)

    def test_history_edit_redirect_routes_transfer_to_transfer_update(self) -> None:
        transfer = StockTransfer.objects.create(
            source_workshop=self.source_workshop,
            destination_workshop=self.destination_workshop,
            user=self.user,
        )

        response = self.client.get(reverse("stock:history_edit", kwargs={"record_type": "transfer", "pk": transfer.pk}))

        self.assertRedirects(response, reverse("stock:transfer_update", kwargs={"pk": transfer.pk}), fetch_redirect_response=False)
