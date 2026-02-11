import gzip
import base64

from lxml import etree

from apps.stock.models import StockPaymentMethod


class NFParser:
    @staticmethod
    def parse_nfe_xml_to_dict(xml_content):
        try:
            if hasattr(xml_content, "read"):
                xml_content = xml_content.read()

            tree = etree.fromstring(xml_content)
            ns = {"ns": "http://www.portalfiscal.inf.br/nfe"}

            # Tenta encontrar docZip (padrão distribuição SEFAZ) ou nfeProc (arquivo XML comum)
            doc_zip = tree.xpath("//ns:docZip", namespaces=ns)

            if doc_zip:
                xml_bin = gzip.decompress(base64.b64decode(doc_zip[0].text))
                nfe_tree = etree.fromstring(xml_bin)
            else:
                # Caso seja o XML direto (upload manual)
                nfe_tree = tree

            # --- Cabeçalho e Fornecedor ---
            emit = nfe_tree.xpath("//ns:emit", namespaces=ns)[0]
            nf_numero = nfe_tree.xpath("//ns:ide/ns:nNF", namespaces=ns)[0].text
            cnpj_fornecedor = emit.xpath("ns:CNPJ", namespaces=ns)[0].text
            nome_fornecedor = emit.xpath("ns:xNome", namespaces=ns)[0].text

            # --- Itens ---
            produtos = []
            detalhes = nfe_tree.xpath("//ns:det", namespaces=ns)
            for det in detalhes:
                produtos.append(
                    {
                        "ref": det.xpath("ns:prod/ns:cProd", namespaces=ns)[0].text,
                        "desc": det.xpath("ns:prod/ns:xProd", namespaces=ns)[0].text,
                        "qtd": str(det.xpath("ns:prod/ns:qCom", namespaces=ns)[0].text),
                        "valor": str(det.xpath("ns:prod/ns:vUnCom", namespaces=ns)[0].text),
                        "ncm": det.xpath("ns:prod/ns:NCM", namespaces=ns)[0].text,
                    }
                )

            # --- Pagamento ---
            pagamentos_sessao = []
            sefaz_map = {
                "01": "DINHEIRO",
                "03": "CREDITO",
                "04": "DEBITO",
                "15": "BOLETO",
                "17": "PIX"
            }

            t_pag_code = tree.xpath('//ns:pag/ns:detPag/ns:tPag/text()', namespaces=ns)
            method_slug = sefaz_map.get(t_pag_code[0], "BOLETO") if t_pag_code else "BOLETO"

            duplicatas = tree.xpath('//ns:cobr/ns:dup', namespaces=ns)
            for idx, dup in enumerate(duplicatas):
                valor = dup.xpath('ns:vDup/text()', namespaces=ns)[0]
                data_vencimento = dup.xpath("ns:dVenc/text()", namespaces=ns)
                data_vencimento = data_vencimento[0] if data_vencimento else ""

                pagamentos_sessao.append({
                    "id": idx + 1,
                    "method": method_slug,
                    "method_display": dict(StockPaymentMethod.PAYMENT_METHOD_CHOICES).get(method_slug),
                    "installments": 1,
                    "first_amount": valor,
                    "total_paid": valor * 1,
                    "payment_date": data_vencimento,
                })
            return {"nf_number": nf_numero, "supplier_cnpj": cnpj_fornecedor, "supplier_name": nome_fornecedor, "items": produtos, "payments": pagamentos_sessao}
        except Exception:
            return None
