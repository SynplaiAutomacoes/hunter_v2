from __future__ import annotations

import html
import logging
from typing import Sequence

from django.conf import settings

from apps.core.domain.contracts.email import (
    EmailConfigurationError,
    EmailServiceError,
    IEmailService,
    SendEmailResponse,
)
from apps.core.infrastructure.gateways.synplaisign import SynplaiSignGatewayError, send_mail as synplaisign_send_mail

logger = logging.getLogger(__name__)


def _system_mail_api_key() -> str:
    api_key = str(getattr(settings, "SYNPLAISIGN_API_KEY", "") or "").strip()
    if api_key:
        return api_key
    return str(getattr(settings, "SYNPLAISIGN_MASTER_KEY", "") or "").strip()


def _default_from_email() -> str:
    return str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()


def plain_text_to_html(body: str) -> str:
    normalized = str(body or "").strip()
    if not normalized:
        return ""
    paragraphs = normalized.split("\n\n")
    rendered: list[str] = []
    for paragraph in paragraphs:
        text = html.escape(paragraph.strip()).replace("\n", "<br>")
        if text:
            rendered.append(f"<p>{text}</p>")
    return "".join(rendered) or f"<p>{html.escape(normalized)}</p>"


def send_transactional_email(
    *,
    to: str | Sequence[str],
    subject: str,
    html_body: str,
    from_email: str | None = None,
    api_key: str | None = None,
) -> SendEmailResponse:
    """Central transactional e-mail sender via SynplaiSign POST /mail (Resend).

    Do not use this for signature envelope delivery — that remains POST /envelopes/:id/send.
    """
    resolved_api_key = str(api_key or "").strip() or _system_mail_api_key()
    if not resolved_api_key:
        raise EmailConfigurationError(
            "Configure SYNPLAISIGN_API_KEY ou SYNPLAISIGN_MASTER_KEY para enviar e-mails."
        )

    resolved_from = str(from_email or "").strip() or _default_from_email() or None
    try:
        result = synplaisign_send_mail(
            api_key=resolved_api_key,
            to=list(to) if not isinstance(to, str) else to,
            subject=subject,
            html=html_body,
            from_email=resolved_from,
        )
    except SynplaiSignGatewayError as exc:
        logger.error("email_service_send_error", extra={"subject": subject, "error": str(exc)})
        raise EmailServiceError(f"Falha ao enviar e-mail: {exc}") from exc

    message_id = result.get("id")
    if result.get("ok") is False:
        raise EmailServiceError("SynplaiSign recusou o envio do e-mail.")

    return SendEmailResponse(
        status="sent",
        message_id=str(message_id) if message_id not in (None, "") else None,
    )


class SynplaiSignEmailService(IEmailService):
    def send(self, to_email: str, subject: str, body: str) -> SendEmailResponse:
        if not to_email or not subject or not body:
            raise EmailServiceError("Destinatário, assunto e corpo são obrigatórios.")
        html_body = plain_text_to_html(body)
        return send_transactional_email(to=to_email, subject=subject, html_body=html_body)


class EmailServiceFactory:
    _instance: IEmailService | None = None

    @classmethod
    def get_service(cls) -> IEmailService:
        if cls._instance is None:
            if not _system_mail_api_key():
                raise EmailConfigurationError(
                    "Configure SYNPLAISIGN_API_KEY ou SYNPLAISIGN_MASTER_KEY para enviar e-mails."
                )
            cls._instance = SynplaiSignEmailService()
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
    """Send a transactional verification code e-mail via SynplaiSign /mail."""
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
