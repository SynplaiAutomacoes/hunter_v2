from __future__ import annotations

from unittest.mock import Mock

from django.test import SimpleTestCase, override_settings

from apps.core.domain.contracts.email import EmailConfigurationError
from apps.core.infrastructure.services.email import (
    EmailServiceFactory,
    build_verification_email_body,
    get_email_service,
    send_verification_code_email,
)


class EmailServiceFactoryTests(SimpleTestCase):
    def setUp(self) -> None:
        EmailServiceFactory._instance = None

    def tearDown(self) -> None:
        EmailServiceFactory._instance = None

    @override_settings(DEFAULT_FROM_EMAIL="", EMAIL_HOST_USER="noreply@hunter.example")
    def test_falls_back_to_email_host_user(self) -> None:
        service = get_email_service()
        self.assertEqual(service._from_email, "noreply@hunter.example")  # type: ignore[attr-defined]

    @override_settings(DEFAULT_FROM_EMAIL="", EMAIL_HOST_USER="")
    def test_raises_when_neither_from_nor_host_user(self) -> None:
        with self.assertRaises(EmailConfigurationError):
            get_email_service()


class SendVerificationCodeEmailTests(SimpleTestCase):
    def setUp(self) -> None:
        EmailServiceFactory._instance = None

    def tearDown(self) -> None:
        EmailServiceFactory._instance = None

    def test_build_body_matches_password_reset_style(self) -> None:
        body = build_verification_email_body(tipo="password_reset", code="ABC123", recipient_name="Ana")
        self.assertIn("Código de recuperação de senha", body)
        self.assertIn("Olá Ana!", body)
        self.assertIn("ABC123", body)
        self.assertIn("Equipe Hunter", body)

    def test_send_verification_code_email_uses_email_service(self) -> None:
        service = Mock()
        EmailServiceFactory.set_service(service)
        ok = send_verification_code_email(
            to_email="ana@example.com",
            code="XYZ789",
            tipo="signup_confirm",
            recipient_name="Ana",
        )
        self.assertTrue(ok)
        service.send.assert_called_once()
        kwargs = service.send.call_args.kwargs
        self.assertEqual(kwargs["to_email"], "ana@example.com")
        self.assertEqual(kwargs["subject"], "Código de confirmação — Hunter Auto")
        self.assertIn("XYZ789", kwargs["body"])

    def test_send_verification_code_email_returns_false_on_failure(self) -> None:
        service = Mock()
        service.send.side_effect = RuntimeError("smtp down")
        EmailServiceFactory.set_service(service)
        ok = send_verification_code_email(to_email="ana@example.com", code="XYZ789", tipo="signup_confirm")
        self.assertFalse(ok)
