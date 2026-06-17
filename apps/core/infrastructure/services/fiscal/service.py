from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from apps.core.domain.contracts.fiscal import (
    DownloadedDocument,
    FiscalServiceError,
    IFiscalService,
)
from apps.core.infrastructure.services.fiscal.config import WebmaniaConfig


class WebmaniaFiscalService(IFiscalService):
    def __init__(self, config: WebmaniaConfig) -> None:
        self._config = config

    def is_homolog_environment(self) -> bool:
        from apps.core.infrastructure.services.webmania.webmania import is_webmania_homolog_environment

        return is_webmania_homolog_environment()

    def emit_nfe(self, *, nfe_request, request=None, slider_override=None) -> dict[str, Any]:
        from apps.core.infrastructure.services.webmania.nfe_emission import NfeEmissionError, emit_nfe_request

        try:
            return emit_nfe_request(nfe_request=nfe_request, request=request, slider_override=slider_override)
        except NfeEmissionError as exc:
            raise FiscalServiceError(str(exc)) from exc

    def sync_nfe_emission_response(self, *, nfe_request, response_payload: dict[str, Any]) -> None:
        from apps.core.infrastructure.services.webmania.nfe_emission import sync_nfe_emission_response

        sync_nfe_emission_response(nfe_request=nfe_request, response_payload=response_payload)

    def cancel_nfe(self, *, workshop, access_key: str, event_uuid: str, reason: str) -> dict[str, Any]:
        from apps.core.infrastructure.services.webmania.nfe_emission import NfeEmissionError, cancel_nfe_document

        try:
            return cancel_nfe_document(workshop=workshop, access_key=access_key, event_uuid=event_uuid, reason=reason)
        except NfeEmissionError as exc:
            raise FiscalServiceError(str(exc)) from exc

    def invalidate_nfe_number(self, *, workshop, number: int, reason: str, series: int, model: int = 1) -> dict[str, Any]:
        from apps.core.infrastructure.services.webmania.nfe_emission import NfeEmissionError, invalidate_nfe_number

        try:
            return invalidate_nfe_number(workshop=workshop, number=number, reason=reason, series=series, model=model)
        except NfeEmissionError as exc:
            raise FiscalServiceError(str(exc)) from exc

    def reconcile_nfe_item(self, *, item) -> Any:
        from apps.core.infrastructure.services.webmania.nfe_consulta import NfeConsultaError, reconcile_nfe_item

        try:
            return reconcile_nfe_item(item=item)
        except NfeConsultaError as exc:
            raise FiscalServiceError(str(exc)) from exc

    def download_nfe_preview_document(self, *, nfe_request, request=None) -> DownloadedDocument:
        from apps.core.infrastructure.services.webmania.nfe_emission import NfeEmissionError, download_nfe_preview_document

        try:
            result = download_nfe_preview_document(nfe_request=nfe_request, request=request)
            return DownloadedDocument(
                content=result.content,
                content_type=result.content_type,
                content_disposition=getattr(result, "content_disposition", ""),
            )
        except NfeEmissionError as exc:
            raise FiscalServiceError(str(exc)) from exc

    def emit_nfse(self, *, nfse_request, request=None, slider_override=None) -> dict[str, Any]:
        from apps.core.infrastructure.services.webmania.emission import NfseEmissionError, emit_nfse_request

        try:
            return emit_nfse_request(nfse_request=nfse_request, request=request, slider_override=slider_override)
        except NfseEmissionError as exc:
            raise FiscalServiceError(str(exc)) from exc

    def sync_nfse_emission_response(self, *, nfse_request, response_payload: dict[str, Any]) -> None:
        from apps.core.infrastructure.services.webmania.emission import sync_emission_response

        sync_emission_response(nfse_request=nfse_request, response_payload=response_payload)

    def cancel_nfse(self, *, workshop, event_uuid: str, reason_code: int) -> dict[str, Any]:
        from apps.core.infrastructure.services.webmania.emission import NfseEmissionError, cancel_nfse_document

        try:
            return cancel_nfse_document(workshop=workshop, event_uuid=event_uuid, reason_code=reason_code)
        except NfseEmissionError as exc:
            raise FiscalServiceError(str(exc)) from exc

    def reconcile_nfse_item(self, *, item) -> Any:
        from apps.core.infrastructure.services.webmania.nfse_consulta import NfseConsultaError, reconcile_nfse_item

        try:
            return reconcile_nfse_item(item=item)
        except NfseConsultaError as exc:
            raise FiscalServiceError(str(exc)) from exc

    def download_nfse_preview_document(self, *, nfse_request, request=None) -> DownloadedDocument:
        from apps.core.infrastructure.services.webmania.emission import NfseEmissionError, download_nfse_preview_document

        try:
            result = download_nfse_preview_document(nfse_request=nfse_request, request=request)
            return DownloadedDocument(
                content=result.content,
                content_type=result.content_type,
                content_disposition=getattr(result, "content_disposition", ""),
            )
        except NfseEmissionError as exc:
            raise FiscalServiceError(str(exc)) from exc

    def download_document(self, *, workshop, url: str) -> DownloadedDocument:
        from apps.core.infrastructure.services.webmania.webmania_documents import (
            WebmaniaDocumentDownloadError,
            download_webmania_document,
        )

        try:
            result = download_webmania_document(workshop=workshop, url=url)
            return DownloadedDocument(
                content=result.content,
                content_type=result.content_type,
                content_disposition=result.content_disposition,
            )
        except WebmaniaDocumentDownloadError as exc:
            raise FiscalServiceError(str(exc)) from exc

    def create_b2b_companies(self, *, quantity: int, workshop=None, force_global: bool = False) -> list[dict[str, Any]]:
        from apps.core.infrastructure.services.webmania.webmania_b2b import WebmaniaB2BServiceError, create_b2b_companies

        try:
            return create_b2b_companies(quantity=quantity, workshop=workshop, force_global=force_global)
        except WebmaniaB2BServiceError as exc:
            raise FiscalServiceError(str(exc)) from exc

    def list_b2b_companies(self, *, workshop=None, force_global_auth: bool = False) -> list[dict[str, Any]]:
        from apps.core.infrastructure.services.webmania.webmania_b2b import WebmaniaB2BServiceError, list_b2b_companies

        try:
            return list_b2b_companies(workshop=workshop, force_global_auth=force_global_auth)
        except WebmaniaB2BServiceError as exc:
            raise FiscalServiceError(str(exc)) from exc

    def sync_b2b_companies_to_database(self, *, workshop=None, actor_user=None, force_global_auth: bool = False) -> list[Any]:
        from apps.core.infrastructure.services.webmania.webmania_b2b import WebmaniaB2BServiceError, sync_b2b_companies_to_database

        try:
            return sync_b2b_companies_to_database(workshop=workshop, actor_user=actor_user, force_global_auth=force_global_auth)
        except WebmaniaB2BServiceError as exc:
            raise FiscalServiceError(str(exc)) from exc

    def list_local_b2b_companies(self, *, workshop=None) -> list[Any]:
        from apps.core.infrastructure.services.webmania.webmania_b2b import list_local_b2b_companies

        return list_local_b2b_companies(workshop=workshop)

    def get_b2b_requests(self, *, month: int | None = None, year: int | None = None, workshop=None) -> dict[str, Any]:
        from apps.core.infrastructure.services.webmania.webmania_b2b import WebmaniaB2BServiceError, get_b2b_requests

        try:
            return get_b2b_requests(month=month, year=year, workshop=workshop)
        except WebmaniaB2BServiceError as exc:
            raise FiscalServiceError(str(exc)) from exc

    def provision_webmania_company_for_workshop(self, *, workshop) -> Any:
        from apps.core.infrastructure.services.webmania.webmania_b2b import WebmaniaB2BServiceError, provision_webmania_company_for_workshop

        try:
            return provision_webmania_company_for_workshop(workshop=workshop)
        except WebmaniaB2BServiceError as exc:
            raise FiscalServiceError(str(exc)) from exc

    def update_webmania_company(self, *, company, payload: dict[str, Any]) -> dict[str, Any]:
        from apps.core.infrastructure.services.webmania.webmania_b2b import WebmaniaB2BServiceError, update_webmania_company

        try:
            return update_webmania_company(company=company, payload=payload)
        except WebmaniaB2BServiceError as exc:
            raise FiscalServiceError(str(exc)) from exc

    def get_context_meta(self, user_account_id) -> dict[str, Any]:
        from apps.core.infrastructure.services.webmania.webmania import get_webmania_context_meta

        return get_webmania_context_meta(user_account_id)

    def save_sync_metadata(self, *, company, error: str = "") -> None:
        from apps.core.infrastructure.services.webmania.webmania import save_company_sync_metadata

        save_company_sync_metadata(company, error=error)

    def encode_workshop_certificate(self, workshop) -> str:
        from apps.core.infrastructure.services.webmania.webmania import encode_workshop_certificate

        return encode_workshop_certificate(workshop)

    def sync_workshop_from_company(self, workshop, company, sync_name: bool = False, sync_address: bool = False) -> None:
        from apps.core.infrastructure.services.webmania.webmania import sync_workshop_from_company

        sync_workshop_from_company(workshop, company, sync_name=sync_name, sync_address=sync_address)
