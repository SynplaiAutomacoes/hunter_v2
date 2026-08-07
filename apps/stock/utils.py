from __future__ import annotations

import base64
import gzip
import json
import logging
from typing import Any

from lxml.etree import QName, fromstring

from apps.finance.models.payment_method import PaymentMethod
from apps.suppliers.models import Supplier


logger = logging.getLogger(__name__)

SEFAZ_NFE_NAMESPACE = {"ns": "http://www.portalfiscal.inf.br/nfe"}


def build_supplier_saved_trigger(supplier: Supplier) -> str:
    return json.dumps({"supplierSaved": {"id": str(supplier.pk), "name": supplier.name}})


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _first_xpath_text(element: Any, xpath: str) -> str | None:
    matches = element.xpath(xpath, namespaces=SEFAZ_NFE_NAMESPACE)
    if not matches:
        return None

    normalized = _normalize_text(matches[0])
    return normalized or None


def extract_nf_number_from_access_key(access_key: object) -> str | None:
    digits = "".join(character for character in _normalize_text(access_key) if character.isdigit())
    if len(digits) != 44:
        return None

    normalized_number = digits[25:34].lstrip("0")
    return normalized_number or "0"


def parse_sefaz_distribution_doc_metadata(xml_content: Any) -> dict[str, str | None] | None:
    if hasattr(xml_content, "xpath"):
        tree = xml_content
    else:
        reader = getattr(xml_content, "read", None)
        if callable(reader):
            xml_content = reader()

        if not xml_content:
            return None

        tree = fromstring(xml_content)

    tag = QName(tree).localname

    if tag == "resNFe":
        access_key = _normalize_text(tree.get("chNFe")) or _first_xpath_text(tree, "ns:chNFe/text()")
        return {
            "key": access_key,
            "nf_number": _normalize_text(tree.get("nNF")) or _first_xpath_text(tree, "ns:nNF/text()") or extract_nf_number_from_access_key(access_key),
            "nome": _normalize_text(tree.get("xNome")) or _first_xpath_text(tree, "ns:xNome/text()"),
            "cnpj": _normalize_text(tree.get("CNPJ") or tree.get("CPF")) or _first_xpath_text(tree, "ns:CNPJ/text()") or _first_xpath_text(tree, "ns:CPF/text()"),
            "valor": _normalize_text(tree.get("vNF")) or _first_xpath_text(tree, "ns:vNF/text()"),
            "data": _normalize_text(tree.get("dhEmi")) or _first_xpath_text(tree, "ns:dhEmi/text()") or _first_xpath_text(tree, "ns:dEmi/text()"),
        }

    access_key = _first_xpath_text(tree, "//ns:infNFe/@Id")
    if access_key:
        access_key = access_key.removeprefix("NFe")

    return {
        "key": access_key,
        "nf_number": _first_xpath_text(tree, "//ns:ide/ns:nNF/text()") or extract_nf_number_from_access_key(access_key),
        "nome": _first_xpath_text(tree, "//ns:emit/ns:xNome/text()"),
        "cnpj": _first_xpath_text(tree, "//ns:emit/ns:CNPJ/text()") or _first_xpath_text(tree, "//ns:emit/ns:CPF/text()"),
        "valor": _first_xpath_text(tree, "//ns:total/ns:ICMSTot/ns:vNF/text()") or _first_xpath_text(tree, "//ns:vNF/text()"),
        "data": _first_xpath_text(tree, "//ns:ide/ns:dhEmi/text()") or _first_xpath_text(tree, "//ns:ide/ns:dEmi/text()"),
    }


class NFParser:
    @staticmethod
    def parse_nfe_xml_to_dict(workshop: Any, xml_content: Any) -> dict[str, Any] | None:
        try:
            reader = getattr(xml_content, "read", None)
            if callable(reader):
                xml_content = reader()

            tree = fromstring(xml_content)

            # Tenta encontrar docZip (padrão distribuição SEFAZ) ou nfeProc (arquivo XML comum)
            doc_zip = tree.xpath("//ns:docZip", namespaces=SEFAZ_NFE_NAMESPACE)

            if doc_zip:
                xml_bin = gzip.decompress(base64.b64decode(doc_zip[0].text))
                nfe_tree = fromstring(xml_bin)
            else:
                # Caso seja o XML direto (upload manual)
                nfe_tree = tree

            if QName(nfe_tree).localname == "resNFe":
                metadata = parse_sefaz_distribution_doc_metadata(nfe_tree)
                if metadata is None:
                    raise ValueError("XML não contém tag resNFe válida.")

                return {
                    "nf_key": metadata.get("key"),
                    "nf_number": metadata.get("nf_number"),
                    "supplier_cnpj": metadata.get("cnpj"),
                    "supplier_name": metadata.get("nome"),
                    "items": [],
                    "payments": [],
                }

            inf_nfe_list = nfe_tree.xpath("//ns:infNFe", namespaces=SEFAZ_NFE_NAMESPACE)
            if not inf_nfe_list:
                raise ValueError("XML não contém tag infNFe ou resNFe válida.")

            infNFe = inf_nfe_list[0]
            chave_acesso = infNFe.get("Id").replace("NFe", "")

            # --- Cabeçalho e Fornecedor ---
            emit = nfe_tree.xpath("//ns:emit", namespaces=SEFAZ_NFE_NAMESPACE)[0]
            nf_numero = _first_xpath_text(nfe_tree, "//ns:ide/ns:nNF/text()") or extract_nf_number_from_access_key(chave_acesso)
            cnpj_fornecedor = _first_xpath_text(emit, "ns:CNPJ/text()") or _first_xpath_text(emit, "ns:CPF/text()") or ""
            nome_fornecedor = _first_xpath_text(emit, "ns:xNome/text()") or ""

            # --- Itens ---
            produtos = []
            detalhes = nfe_tree.xpath("//ns:det", namespaces=SEFAZ_NFE_NAMESPACE)
            for det in detalhes:
                produtos.append(
                    {
                        "ref": det.xpath("ns:prod/ns:cProd", namespaces=SEFAZ_NFE_NAMESPACE)[0].text,
                        "desc": det.xpath("ns:prod/ns:xProd", namespaces=SEFAZ_NFE_NAMESPACE)[0].text,
                        "qtd": str(det.xpath("ns:prod/ns:qCom", namespaces=SEFAZ_NFE_NAMESPACE)[0].text),
                        "valor": str(det.xpath("ns:prod/ns:vUnCom", namespaces=SEFAZ_NFE_NAMESPACE)[0].text),
                        "ncm": det.xpath("ns:prod/ns:NCM", namespaces=SEFAZ_NFE_NAMESPACE)[0].text,
                    }
                )

            # --- Pagamento ---
            pagamentos_sessao = []
            sefaz_map = {"01": "DINHEIRO", "03": "CREDITO", "04": "DEBITO", "15": "BOLETO", "17": "PIX"}

            t_pag_code = nfe_tree.xpath("//ns:pag/ns:detPag/ns:tPag/text()", namespaces=SEFAZ_NFE_NAMESPACE)
            method_slug = sefaz_map.get(t_pag_code[0], "BOLETO") if t_pag_code else "BOLETO"

            duplicatas = nfe_tree.xpath("//ns:cobr/ns:dup", namespaces=SEFAZ_NFE_NAMESPACE)
            for idx, dup in enumerate(duplicatas):
                valor = dup.xpath("ns:vDup/text()", namespaces=SEFAZ_NFE_NAMESPACE)[0]
                data_vencimento = dup.xpath("ns:dVenc/text()", namespaces=SEFAZ_NFE_NAMESPACE)
                data_vencimento = data_vencimento[0] if data_vencimento else ""

                method_obj, _ = PaymentMethod.objects.get_or_create(
                    workshop=workshop,
                    description=method_slug,
                    defaults={
                        "is_active": True,
                        "payment_type": PaymentMethod.infer_payment_type(method_slug),
                    },
                )

                pagamentos_sessao.append(
                    {
                        "id": idx + 1,
                        "method": getattr(method_obj, "pk", None),
                        "method_display": getattr(method_obj, "description", method_slug),
                        "installments": 1,
                        "first_amount": valor,
                        "total_paid": valor * 1,
                        "payment_date": data_vencimento,
                    }
                )
            return {"nf_key": chave_acesso, "nf_number": nf_numero, "supplier_cnpj": cnpj_fornecedor, "supplier_name": nome_fornecedor, "items": produtos, "payments": pagamentos_sessao}
        except Exception:
            logger.exception("Erro no parsing do XML")
            return None
