from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class EmailServiceError(Exception):
    pass


class EmailConfigurationError(Exception):
    pass


@dataclass(frozen=True)
class SendEmailResponse:
    status: str


class IEmailService(ABC):
    @abstractmethod
    def send(self, to_email: str, subject: str, body: str) -> SendEmailResponse:
        pass
