from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from apps.core.documents.services import SignatureDeliveryServiceError


@override_settings(APP_BASE_URL="https://app.example.com")
class SignatureWebhookCommandTests(SimpleTestCase):
    @patch("apps.budget.management.commands.webhook.ensure_signature_webhook")
    def test_command_prints_success_when_webhook_is_synced(self, ensure_webhook_mock: MagicMock) -> None:
        ensure_webhook_mock.return_value = {"id": "wh-1"}
        stdout = StringIO()
        stderr = StringIO()

        call_command("webhook", stdout=stdout, stderr=stderr, no_color=True)

        expected_url = f"https://app.example.com{reverse('budget:supersign_webhook')}"
        ensure_webhook_mock.assert_called_once_with(webhook_url=expected_url)
        self.assertIn(f"SuperSign webhook sincronizado: wh-1 -> {expected_url}", stdout.getvalue())
        self.assertEqual("", stderr.getvalue())

    @patch("apps.budget.management.commands.webhook.ensure_signature_webhook")
    def test_command_warns_and_continues_when_sync_fails(self, ensure_webhook_mock: MagicMock) -> None:
        ensure_webhook_mock.side_effect = SignatureDeliveryServiceError("timeout")
        stdout = StringIO()
        stderr = StringIO()

        call_command("webhook", stdout=stdout, stderr=stderr, no_color=True)

        expected_url = f"https://app.example.com{reverse('budget:supersign_webhook')}"
        self.assertEqual("", stdout.getvalue())
        self.assertIn(f"SuperSign webhook nao sincronizado: {expected_url}", stderr.getvalue())
        self.assertIn("timeout", stderr.getvalue())

    @patch("apps.budget.management.commands.webhook.ensure_signature_webhook")
    def test_command_raises_in_strict_mode_when_sync_fails(self, ensure_webhook_mock: MagicMock) -> None:
        ensure_webhook_mock.side_effect = SignatureDeliveryServiceError("timeout")

        with self.assertRaisesMessage(CommandError, "SuperSign webhook nao sincronizado"):
            call_command("webhook", strict=True, no_color=True)
