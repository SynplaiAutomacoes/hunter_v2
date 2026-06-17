from __future__ import annotations

from apps.core.domain.contracts.sefaz import ISefazService
from apps.core.infrastructure.services.sefaz.service import PynfeSefazService


class SefazServiceProvider:
    _instance: ISefazService | None = None

    @classmethod
    def get_service(cls) -> ISefazService:
        if cls._instance is None:
            cls._instance = PynfeSefazService()
        return cls._instance

    @classmethod
    def set_service(cls, service: ISefazService) -> None:
        cls._instance = service


def get_sefaz_service() -> ISefazService:
    return SefazServiceProvider.get_service()


def set_sefaz_service(service: ISefazService) -> None:
    SefazServiceProvider.set_service(service)
