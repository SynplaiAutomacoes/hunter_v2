from __future__ import annotations

import base64
import gzip
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from apps.stock.forms import ImportSefazListForm
from apps.stock.models import SefazZipCache, StockImport
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
            pfx_certificate="certificados/teste.pfx",
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
