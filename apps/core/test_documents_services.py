from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.core.documents.gateways.supersign import SuperSignGatewayError
from apps.core.documents.services import (
    SignatureDeliveryServiceError,
    create_signature_webhook,
    ensure_signature_webhook,
    list_signature_webhooks,
)


class SignatureWebhookServiceTests(SimpleTestCase):
    @patch("apps.core.documents.services.list_supersign_webhooks_request")
    def test_list_signature_webhooks_returns_gateway_payload(self, list_webhooks_mock) -> None:
        list_webhooks_mock.return_value = [{"id": "wh-1", "url": "https://example.com/hook"}]

        result = list_signature_webhooks()

        self.assertEqual(result, [{"id": "wh-1", "url": "https://example.com/hook"}])

    @patch("apps.core.documents.services.list_supersign_webhooks_request")
    def test_list_signature_webhooks_translates_gateway_errors(self, list_webhooks_mock) -> None:
        list_webhooks_mock.side_effect = SuperSignGatewayError("boom")

        with self.assertRaises(SignatureDeliveryServiceError):
            list_signature_webhooks()

    @patch("apps.core.documents.services.create_supersign_webhook_request")
    def test_create_signature_webhook_translates_gateway_payload(self, create_webhook_mock) -> None:
        create_webhook_mock.return_value = {"id": "wh-2", "events": ["ENVELOPE_COMPLETED"]}

        result = create_signature_webhook(url="https://example.com/hook")

        self.assertEqual(result["id"], "wh-2")
        create_webhook_mock.assert_called_once_with(
            url="https://example.com/hook",
            events=None,
            is_active=True,
        )

    @patch("apps.core.documents.services.list_signature_webhooks")
    @patch("apps.core.documents.services.create_signature_webhook")
    def test_ensure_signature_webhook_reuses_existing_matching_webhook(self, create_webhook_mock, list_webhooks_mock) -> None:
        list_webhooks_mock.return_value = [
            {
                "id": "wh-1",
                "url": "https://example.com/hook",
                "events": ["ENVELOPE_COMPLETED", "OTHER_EVENT"],
            }
        ]

        result = ensure_signature_webhook(webhook_url="https://example.com/hook")

        self.assertEqual(result["id"], "wh-1")
        create_webhook_mock.assert_not_called()

    @patch("apps.core.documents.services.list_signature_webhooks")
    @patch("apps.core.documents.services.create_signature_webhook")
    def test_ensure_signature_webhook_creates_when_missing(self, create_webhook_mock, list_webhooks_mock) -> None:
        list_webhooks_mock.return_value = []
        create_webhook_mock.return_value = {"id": "wh-3"}

        result = ensure_signature_webhook(webhook_url="https://example.com/hook")

        self.assertEqual(result, {"id": "wh-3"})
        create_webhook_mock.assert_called_once_with(
            url="https://example.com/hook",
            events=["ENVELOPE_COMPLETED"],
            is_active=True,
        )
