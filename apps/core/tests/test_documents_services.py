from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.core.documents.contract import SignatureDeliveryResult
from apps.core.documents.gateways.supersign import SuperSignGatewayError, SuperSignGatewayResult
from apps.core.documents.services import (
    SignatureDeliveryServiceError,
    create_signature_webhook,
    download_signed_document_content,
    ensure_signature_webhook,
    list_signature_webhooks,
    send_document_for_signature,
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


class SignatureDeliveryServiceTests(SimpleTestCase):
    @patch("apps.core.documents.services.send_pdf_for_signature")
    def test_send_document_for_signature_maps_gateway_result(self, send_pdf_mock) -> None:
        send_pdf_mock.return_value = SuperSignGatewayResult(
            envelope_id="env-1",
            document_id="doc-1",
            raw_response={"ok": True},
        )

        result = send_document_for_signature(
            pdf_bytes=b"pdf",
            file_name="arquivo.pdf",
            document_ref_id="budget-1",
            title="Titulo",
            message="Mensagem",
            signatory={"id": "customer-1"},
            observers=[],
            fields=[{"type": "SIGNATURE"}],
            folder_id="folder-1",
        )

        self.assertEqual(
            result,
            SignatureDeliveryResult(
                envelope_id="env-1",
                document_id="doc-1",
                provider="supersign",
                raw_response={"ok": True},
            ),
        )

    @patch("apps.core.documents.services.send_pdf_for_signature")
    def test_send_document_for_signature_translates_gateway_errors(self, send_pdf_mock) -> None:
        send_pdf_mock.side_effect = SuperSignGatewayError("boom")

        with self.assertRaises(SignatureDeliveryServiceError):
            send_document_for_signature(
                pdf_bytes=b"pdf",
                file_name="arquivo.pdf",
                document_ref_id="budget-1",
                title="Titulo",
                message="Mensagem",
                signatory={"id": "customer-1"},
                observers=[],
                fields=[{"type": "SIGNATURE"}],
                folder_id="folder-1",
            )

    @patch("apps.core.documents.services.download_signed_document")
    def test_download_signed_document_content_returns_gateway_bytes(self, download_mock) -> None:
        download_mock.return_value = b"pdf-assinado"

        result = download_signed_document_content(document_id="doc-1")

        self.assertEqual(result, b"pdf-assinado")

    @patch("apps.core.documents.services.download_signed_document")
    def test_download_signed_document_content_translates_gateway_errors(self, download_mock) -> None:
        download_mock.side_effect = SuperSignGatewayError("boom")

        with self.assertRaises(SignatureDeliveryServiceError):
            download_signed_document_content(document_id="doc-1")
