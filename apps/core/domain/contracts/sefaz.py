from __future__ import annotations

from abc import ABC, abstractmethod


class SefazServiceError(Exception):
    pass


class ISefazService(ABC):
    @abstractmethod
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
        """
        Consulta a distribuição de documentos na SEFAZ.

        Se `chave` for fornecida: baixa NF-e específica pela chave de acesso.
        Se `chave` for None: consulta por NSU (lote de documentos novos).

        Retorna o XML de resposta completo (raw bytes).
        """
        ...
