from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.core.domain.contracts.email import EmailConfigurationError, EmailServiceError
from apps.core.infrastructure.gateways.synplaisign import SynplaiSignGatewayError
from apps.core.infrastructure.services.email import (
    EmailServiceFactory,
    build_verification_email_body,
    get_email_service,
    plain_text_to_html,
    send_transactional_email,
    send_verification_code_email,
)


class EmailServiceFactoryTests(SimpleTestCase):
    def setUp(self) -> None:
        EmailServiceFactory._instance = None

    def tearDown(self) -> None:
        EmailServiceFactory._instance = None

    @override_settings(SYNPLAISIGN_API_KEY="", SYNPLAISIGN_MASTER_KEY="sk_master_test")
    def test_get_service_accepts_master_key(self) -> None:
        service = get_email_service()
        self.assertIsNotNone(service)

    @override_settings(SYNPLAISIGN_API_KEY="", SYNPLAISIGN_MASTER_KEY="")
    def test_raises_when_no_synplaisign_key(self) -> None:
        with self.assertRaises(EmailConfigurationError):
            get_email_service()


class SendTransactionalEmailTests(SimpleTestCase):
    def setUp(self) -> None:
        EmailServiceFactory._instance = None

    def tearDown(self) -> None:
        EmailServiceFactory._instance = None

    def test_plain_text_to_html_escapes_and_preserves_breaks(self) -> None:
        html_body = plain_text_to_html("Olá <Ana>!\n\nCódigo: ABC")
        self.assertIn("<p>Olá &lt;Ana&gt;!</p>", html_body)
        self.assertIn("<p>Código: ABC</p>", html_body)

    @override_settings(SYNPLAISIGN_API_KEY="sk_live_test", DEFAULT_FROM_EMAIL="Hunter <noreply@hunter.test>")
    @patch("apps.core.infrastructure.services.email.synplaisign_send_mail")
    def test_send_transactional_email_calls_synplaisign_mail(self, send_mail: Mock) -> None:
        send_mail.return_value = {"ok": True, "id": "re_123"}
        result = send_transactional_email(
            to="ana@example.com",
            subject="Orçamento #1",
            html_body="<p>Olá</p>",
        )
        self.assertEqual(result.status, "sent")
        self.assertEqual(result.message_id, "re_123")
        send_mail.assert_called_once_with(
            api_key="sk_live_test",
            to="ana@example.com",
            subject="Orçamento #1",
            html="<p>Olá</p>",
            from_email="Hunter <noreply@hunter.test>",
        )

    @override_settings(SYNPLAISIGN_API_KEY="sk_live_test", DEFAULT_FROM_EMAIL="")
    @patch("apps.core.infrastructure.services.email.synplaisign_send_mail")
    def test_send_transactional_email_omits_from_when_unset(self, send_mail: Mock) -> None:
        send_mail.return_value = {"ok": True, "id": None}
        send_transactional_email(to=["a@x.com", "b@x.com"], subject="Hi", html_body="<p>x</p>")
        self.assertEqual(send_mail.call_args.kwargs["from_email"], None)
        self.assertEqual(send_mail.call_args.kwargs["to"], ["a@x.com", "b@x.com"])

    @override_settings(SYNPLAISIGN_API_KEY="sk_live_test")
    @patch("apps.core.infrastructure.services.email.synplaisign_send_mail")
    def test_send_transactional_email_maps_gateway_error(self, send_mail: Mock) -> None:
        send_mail.side_effect = SynplaiSignGatewayError("boom")
        with self.assertRaises(EmailServiceError):
            send_transactional_email(to="ana@example.com", subject="Hi", html_body="<p>x</p>")


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

    @override_settings(SYNPLAISIGN_MASTER_KEY="sk_master_test", SYNPLAISIGN_API_KEY="", DEFAULT_FROM_EMAIL="")
    @patch("apps.core.infrastructure.services.email.synplaisign_send_mail")
    def test_send_verification_code_email_uses_mail_endpoint(self, send_mail: Mock) -> None:
        send_mail.return_value = {"ok": True, "id": "re_abc"}
        ok = send_verification_code_email(
            to_email="ana@example.com",
            code="XYZ789",
            tipo="signup_confirm",
            recipient_name="Ana",
        )
        self.assertTrue(ok)
        send_mail.assert_called_once()
        kwargs = send_mail.call_args.kwargs
        self.assertEqual(kwargs["api_key"], "sk_master_test")
        self.assertEqual(kwargs["to"], "ana@example.com")
        self.assertEqual(kwargs["subject"], "Código de confirmação — Hunter Auto")
        self.assertIn("XYZ789", kwargs["html"])
        self.assertIn("<p>", kwargs["html"])

    @override_settings(SYNPLAISIGN_MASTER_KEY="sk_master_test", SYNPLAISIGN_API_KEY="")
    @patch("apps.core.infrastructure.services.email.synplaisign_send_mail")
    def test_send_verification_code_email_returns_false_on_failure(self, send_mail: Mock) -> None:
        send_mail.side_effect = SynplaiSignGatewayError("smtp down")
        ok = send_verification_code_email(to_email="ana@example.com", code="XYZ789", tipo="signup_confirm")
        self.assertFalse(ok)
