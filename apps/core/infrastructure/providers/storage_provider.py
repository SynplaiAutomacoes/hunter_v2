from __future__ import annotations

from functools import lru_cache

from django.conf import settings

from apps.core.domain.contracts.storage import IStorageService
from apps.core.infrastructure.services.storage import S3StorageService


class StorageServiceProvider:
    _instance: IStorageService | None = None

    @classmethod
    def get_service(cls) -> IStorageService:
        if cls._instance is None:
            cls._instance = S3StorageService(
                access_key_id=str(getattr(settings, "STORAGE_ACCESS_KEY_ID", "") or ""),
                secret_access_key=str(getattr(settings, "STORAGE_SECRET_ACCESS_KEY", "") or ""),
                bucket=str(getattr(settings, "STORAGE_BUCKET", "") or ""),
                endpoint=str(getattr(settings, "STORAGE_ENDPOINT", "") or ""),
                region=str(getattr(settings, "STORAGE_REGION", "auto") or "auto"),
            )
        return cls._instance

    @classmethod
    def set_service(cls, service: IStorageService) -> None:
        cls._instance = service


def get_storage_service() -> IStorageService:
    return StorageServiceProvider.get_service()


def set_storage_service(service: IStorageService) -> None:
    StorageServiceProvider.set_service(service)
