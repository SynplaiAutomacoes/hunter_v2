from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.core.domain.contracts.email import EmailConfigurationError
from apps.core.infrastructure.services.email import EmailServiceFactory, get_email_service


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
