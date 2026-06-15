from __future__ import annotations

from django.conf import settings

from apps.core.domain.contracts.signature import ISignatureService
from apps.core.infrastructure.services.signature_supersign import SuperSignSignatureService


class SignatureServiceProvider:
    _instance: ISignatureService | None = None

    @classmethod
    def get_service(cls) -> ISignatureService:
        if cls._instance is None:
            cls._instance = SuperSignSignatureService()
        return cls._instance

    @classmethod
    def set_service(cls, service: ISignatureService) -> None:
        cls._instance = service


def get_signature_service() -> ISignatureService:
    return SignatureServiceProvider.get_service()


def set_signature_service(service: ISignatureService) -> None:
    SignatureServiceProvider.set_service(service)
