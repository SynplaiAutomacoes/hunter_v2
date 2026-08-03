from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

from apps.core.domain.contracts.email import (
    EmailConfigurationError,
    EmailServiceError,
    IEmailService,
    SendEmailResponse,
)

logger = logging.getLogger(__name__)


class DjangoSmtpEmailService(IEmailService):
    def __init__(self, from_email: str) -> None:
        normalized_from_email = str(from_email or "").strip()
        if not normalized_from_email:
            raise EmailConfigurationError("Configure DEFAULT_FROM_EMAIL para enviar e-mails.")
        self._from_email = normalized_from_email

    def send(self, to_email: str, subject: str, body: str) -> SendEmailResponse:
        if not to_email or not subject or not body:
            raise EmailServiceError("Destinatário, assunto e corpo são obrigatórios.")
        try:
            sent = send_mail(
                subject=subject,
                message=body,
                from_email=self._from_email,
                recipient_list=[to_email],
                fail_silently=False,
            )
        except Exception as e:
            logger.error("email_service_send_error", extra={"to": to_email, "subject": subject, "error": str(e)})
            raise EmailServiceError(f"Falha ao enviar e-mail: {e}") from e

        if not sent:
            logger.warning("email_service_send_ignored", extra={"to": to_email, "subject": subject})
            return SendEmailResponse(status="ignored")

        return SendEmailResponse(status="sent")


class EmailServiceFactory:
    _instance: IEmailService | None = None

    @classmethod
    def get_service(cls) -> IEmailService:
        if cls._instance is None:
            from_email = str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
            if not from_email:
                raise EmailConfigurationError("Configure DEFAULT_FROM_EMAIL nas settings do Django.")
            cls._instance = DjangoSmtpEmailService(from_email=from_email)
        return cls._instance

    @classmethod
    def set_service(cls, service: IEmailService) -> None:
        cls._instance = service


def get_email_service() -> IEmailService:
    return EmailServiceFactory.get_service()
