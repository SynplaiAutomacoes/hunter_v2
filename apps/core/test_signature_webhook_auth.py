from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.infrastructure.services.signature_webhook import validate_signature_webhook_request


class SignatureWebhookAuthTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @override_settings(DEBUG=False, SYNPLAISIGN_WEBHOOK_SECRET="")
    def test_missing_secrets_rejected_when_not_debug(self) -> None:
        request = self.factory.post("/budget/signature/webhook/", data=b"{}", content_type="application/json")
        response = validate_signature_webhook_request(request, workshop_secret="")
        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(response.status_code, 401)

    @override_settings(DEBUG=True, SYNPLAISIGN_WEBHOOK_SECRET="")
    def test_missing_secrets_allowed_in_debug(self) -> None:
        request = self.factory.post("/budget/signature/webhook/", data=b"{}", content_type="application/json")
        response = validate_signature_webhook_request(request, workshop_secret="")
        self.assertIsNone(response)
