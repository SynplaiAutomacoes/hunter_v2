from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class StorageServiceError(Exception):
    pass


class StorageConfigurationError(Exception):
    pass


@dataclass(frozen=True)
class StorageObject:
    key: str
    content: bytes
    content_type: str
    metadata: dict[str, str]


class IStorageService(ABC):
    @abstractmethod
    def upload_file(self, file: bytes, key: str, *, content_type: str = "application/octet-stream", metadata: dict[str, str] | None = None) -> None:
        ...

    @abstractmethod
    def read_file(self, key: str) -> StorageObject:
        ...

    @abstractmethod
    def delete_file(self, key: str) -> None:
        ...

    @abstractmethod
    def generate_presigned_url(self, key: str, *, expires_in: int = 3600) -> str:
        ...
