from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import IO


class WhatsAppServiceError(Exception):
    pass


class WhatsAppConfigurationError(Exception):
    pass


@dataclass(frozen=True)
class SendTextResponse:
    status: str
    response: dict


@dataclass(frozen=True)
class SendFileResponse:
    status: str
    detail: str
    number: str
    media_url: str


@dataclass(frozen=True)
class HealthCheckResponse:
    status: str


class IWhatsAppService(ABC):
    @abstractmethod
    def health_check(self) -> HealthCheckResponse:
        pass

    @abstractmethod
    def send_text(self, number: str, text: str) -> SendTextResponse:
        pass

    @abstractmethod
    def send_file(self, number: str, file: IO, filename: str, text: str | None = None) -> SendFileResponse:
        pass

    @abstractmethod
    def send_file_from_url(self, number: str, file_url: str, text: str | None = None, filename: str | None = None, mimetype: str | None = None) -> SendFileResponse:
        pass
