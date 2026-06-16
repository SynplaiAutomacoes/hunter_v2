from __future__ import annotations

from apps.core.domain.contracts.sefaz import ISefazService


class PynfeSefazService(ISefazService):
    def consultar_distribuicao(
        self,
        *,
        certificado_path: str,
        certificado_senha: str,
        uf: str,
        cnpj: str,
        nsu: str = "0",
        chave: str | None = None,
    ) -> bytes:
        from pynfe.processamento import ComunicacaoSefaz

        comunicacao = ComunicacaoSefaz(uf, certificado_path, certificado_senha)

        if chave is not None:
            xml_response = comunicacao.consulta_distribuicao(cnpj=cnpj, chave=chave)
        else:
            xml_response = comunicacao.consulta_distribuicao(cnpj=cnpj, nsu=nsu)

        return xml_response.content
