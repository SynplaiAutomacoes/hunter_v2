from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class FiscalServiceError(Exception):
    pass


@dataclass(frozen=True)
class DownloadedDocument:
    content: bytes
    content_type: str
    content_disposition: str


@dataclass(frozen=True)
class B2BCompanyPayload:
    webmania_company_id: str
    cnpj: str
    razao_social: str
    nome_completo: str
    cpf: str
    ie: str
    cidade: str
    uf: str
    unidade_empresa: str
    tipo_tributacao: str
    telefone: str
    endereco: str
    numero: str
    complemento: str
    credentials: dict[str, str]


class IFiscalService(ABC):
    @abstractmethod
    def is_homolog_environment(self) -> bool:
        ...

    @abstractmethod
    def emit_nfe(self, *, nfe_request, request=None, slider_override=None) -> dict[str, Any]:
        ...

    @abstractmethod
    def sync_nfe_emission_response(self, *, nfe_request, response_payload: dict[str, Any]) -> None:
        ...

    @abstractmethod
    def cancel_nfe(self, *, workshop, access_key: str, event_uuid: str, reason: str) -> dict[str, Any]:
        ...

    @abstractmethod
    def invalidate_nfe_number(self, *, workshop, number: int, reason: str, series: int, model: int = 1) -> dict[str, Any]:
        ...

    @abstractmethod
    def reconcile_nfe_item(self, *, item) -> Any:
        ...

    @abstractmethod
    def download_nfe_preview_document(self, *, nfe_request, request=None) -> DownloadedDocument:
        ...

    @abstractmethod
    def emit_nfse(self, *, nfse_request, request=None, slider_override=None) -> dict[str, Any]:
        ...

    @abstractmethod
    def sync_nfse_emission_response(self, *, nfse_request, response_payload: dict[str, Any]) -> None:
        ...

    @abstractmethod
    def cancel_nfse(self, *, workshop, event_uuid: str, reason_code: int) -> dict[str, Any]:
        ...

    @abstractmethod
    def reconcile_nfse_item(self, *, item) -> Any:
        ...

    @abstractmethod
    def download_nfse_preview_document(self, *, nfse_request, request=None) -> DownloadedDocument:
        ...

    @abstractmethod
    def download_document(self, *, workshop, url: str) -> DownloadedDocument:
        ...

    @abstractmethod
    def create_b2b_companies(self, *, quantity: int, workshop=None, force_global: bool = False) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def list_b2b_companies(self, *, workshop=None, force_global_auth: bool = False) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def sync_b2b_companies_to_database(self, *, workshop=None, actor_user=None, force_global_auth: bool = False) -> list[Any]:
        ...

    @abstractmethod
    def list_local_b2b_companies(self, *, workshop=None) -> list[Any]:
        ...

    @abstractmethod
    def get_b2b_requests(self, *, month: int | None = None, year: int | None = None, workshop=None) -> dict[str, Any]:
        ...

    @abstractmethod
    def provision_webmania_company_for_workshop(self, *, workshop) -> Any:
        ...

    @abstractmethod
    def update_webmania_company(self, *, company, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    def get_context_meta(self, user_account_id) -> dict[str, Any]:
        ...

    @abstractmethod
    def save_sync_metadata(self, *, company, error: str = "") -> None:
        ...

    @abstractmethod
    def encode_workshop_certificate(self, workshop) -> str:
        ...

    @abstractmethod
    def sync_workshop_from_company(self, workshop, company, sync_name: bool = False, sync_address: bool = False) -> None:
        ...
