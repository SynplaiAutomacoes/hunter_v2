from __future__ import annotations

from django.test import SimpleTestCase, override_settings
from django.test.client import RequestFactory

from apps.messaging.presentation.views.dispatch_status_views import MessageDispatchStatusIngestView


class DispatchStatusAuthTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.view = MessageDispatchStatusIngestView()

    @override_settings(DEBUG=False, MESSAGE_DISPATCH_STATUS_TOKEN="")
    def test_empty_token_rejected_when_not_debug(self) -> None:
        request = self.factory.post("/messaging/dispatch/status/")
        self.assertFalse(MessageDispatchStatusIngestView._is_authorized(request))

    @override_settings(DEBUG=True, MESSAGE_DISPATCH_STATUS_TOKEN="")
    def test_empty_token_allowed_in_debug(self) -> None:
        request = self.factory.post("/messaging/dispatch/status/")
        self.assertTrue(MessageDispatchStatusIngestView._is_authorized(request))

    @override_settings(DEBUG=False, MESSAGE_DISPATCH_STATUS_TOKEN="expected-token")
    def test_constant_time_token_match(self) -> None:
        bad = self.factory.post("/messaging/dispatch/status/", HTTP_X_DISPATCH_STATUS_TOKEN="wrong")
        good = self.factory.post("/messaging/dispatch/status/", HTTP_X_DISPATCH_STATUS_TOKEN="expected-token")
        self.assertFalse(MessageDispatchStatusIngestView._is_authorized(bad))
        self.assertTrue(MessageDispatchStatusIngestView._is_authorized(good))
