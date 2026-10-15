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
                from_email = str(getattr(settings, "EMAIL_HOST_USER", "") or "").strip()
            if not from_email:
                raise EmailConfigurationError(
                    "Configure DEFAULT_FROM_EMAIL (ou EMAIL_HOST_USER) nas settings do Django."
                )
            cls._instance = DjangoSmtpEmailService(from_email=from_email)
        return cls._instance

    @classmethod
    def set_service(cls, service: IEmailService) -> None:
        cls._instance = service


def get_email_service() -> IEmailService:
    return EmailServiceFactory.get_service()


_VERIFICATION_EMAIL_SUBJECTS: dict[str, str] = {
    "password_reset": "Código de recuperação de senha",
    "login_code": "Código de login",
    "signup_confirm": "Código de confirmação — Hunter Auto",
}

_VERIFICATION_EMAIL_BODIES: dict[str, dict[str, str]] = {
    "password_reset": {
        "titulo": "Código de recuperação de senha",
        "texto": "Seu código de verificação é",
        "expira": "15 minutos",
    },
    "login_code": {
        "titulo": "Código de login",
        "texto": "Seu código de acesso é",
        "expira": "5 minutos",
    },
    "signup_confirm": {
        "titulo": "Código de confirmação de e-mail",
        "texto": "Seu código de confirmação para criar a conta Hunter Auto é",
        "expira": "15 minutos",
    },
}


def mask_email(email: str) -> str:
    if not email:
        return email
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    if len(local) <= 2:
        return email
    return f"{local[:2]}{'*' * (len(local) - 2)}@{domain}"


def build_verification_email_body(*, tipo: str, code: str, recipient_name: str = "") -> str:
    data = _VERIFICATION_EMAIL_BODIES[tipo]
    name = (recipient_name or "").strip()
    greeting = f"Olá {name}!" if name else "Olá!"
    return (
        f"{data['titulo']}\n\n"
        f"{greeting}\n\n"
        f"{data['texto']}: {code}\n\n"
        f"Este código expira em {data['expira']}.\n\n"
        "Se você não solicitou esta ação, ignore esta mensagem.\n\n"
        "Equipe Hunter"
    )


def send_verification_code_email(
    *,
    to_email: str,
    code: str,
    tipo: str,
    recipient_name: str = "",
    user_id: int | None = None,
) -> bool:
    """Send a transactional verification code e-mail. Same path used by password reset / login."""
    normalized = str(to_email or "").strip().lower()
    if not normalized:
        logger.warning("user_email_missing", extra={"user_id": user_id, "tipo": tipo})
        return False
    if tipo not in _VERIFICATION_EMAIL_SUBJECTS:
        logger.error("email_unknown_tipo", extra={"tipo": tipo, "user_id": user_id})
        return False

    try:
        get_email_service().send(
            to_email=normalized,
            subject=_VERIFICATION_EMAIL_SUBJECTS[tipo],
            body=build_verification_email_body(tipo=tipo, code=code, recipient_name=recipient_name),
        )
        logger.info(
            "email_sent",
            extra={"to": mask_email(normalized), "tipo": tipo, "user_id": user_id},
        )
        return True
    except Exception as exc:
        logger.error(
            "email_send_failed",
            extra={"user_id": user_id, "tipo": tipo, "error": str(exc)},
        )
        return False
