from __future__ import annotations

from django.conf import settings

from apps.core.domain.contracts.fiscal import IFiscalService
from apps.core.infrastructure.services.fiscal.config import WebmaniaConfig
from apps.core.infrastructure.services.fiscal.service import WebmaniaFiscalService


class FiscalServiceProvider:
    _instance: IFiscalService | None = None

    @classmethod
    def get_service(cls) -> IFiscalService:
        if cls._instance is None:
            config = WebmaniaConfig(
                base_url=str(getattr(settings, "WEBMANIA_BASE_URL", "")),
                b2b_base_url=str(getattr(settings, "WEBMANIA_B2B_BASE_URL", "")),
                ambient=int(getattr(settings, "WEBMANIA_AMBIENT", 2)),
                api_key=str(getattr(settings, "WEBMANIA_API_KEY", "")),
                consumer_key=str(getattr(settings, "WEBMANIA_CONSUMER_KEY", "")),
                consumer_secret=str(getattr(settings, "WEBMANIA_CONSUMER_SECRET", "")),
                access_token=str(getattr(settings, "WEBMANIA_ACCESS_TOKEN", "")),
                access_token_secret=str(getattr(settings, "WEBMANIA_ACCESS_TOKEN_SECRET", "")),
                b2b_consumer_key=str(getattr(settings, "WEBMANIA_B2B_CONSUMER_KEY", "")),
                b2b_consumer_secret=str(getattr(settings, "WEBMANIA_B2B_CONSUMER_SECRET", "")),
                b2b_access_token=str(getattr(settings, "WEBMANIA_B2B_ACCESS_TOKEN", "")),
                b2b_access_token_secret=str(getattr(settings, "WEBMANIA_B2B_ACCESS_TOKEN_SECRET", "")),
                webhook_token=str(getattr(settings, "WEBMANIA_WEBHOOK_TOKEN", "")),
                tax_class_base_url=str(getattr(settings, "WEBMANIA_TAX_CLASS_BASE_URL", "")),
                nfe_consulta_endpoint=str(getattr(settings, "WEBMANIA_NFE_CONSULTA_ENDPOINT", "")),
                nfse_consulta_endpoint=str(getattr(settings, "WEBMANIA_NFSE_CONSULTA_ENDPOINT", "")),
            )
            cls._instance = WebmaniaFiscalService(config=config)
        return cls._instance

    @classmethod
    def set_service(cls, service: IFiscalService) -> None:
        cls._instance = service


def get_fiscal_service() -> IFiscalService:
    return FiscalServiceProvider.get_service()


def set_fiscal_service(service: IFiscalService) -> None:
    FiscalServiceProvider.set_service(service)
