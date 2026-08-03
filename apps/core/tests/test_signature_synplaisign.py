from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.core.domain.contracts.signature import SignatureSendRequest, SignatureSendResult
from apps.core.infrastructure.gateways.synplaisign import (
    SynplaiSignGatewayResult,
    build_signing_url,
)
from apps.core.infrastructure.providers import set_signature_service
from apps.core.infrastructure.services.signature_synplaisign import SynplaiSignSignatureService, _map_signatories
from apps.core.infrastructure.services.signature_webhook import (
    SignatureWebhookView,
    build_synplaisign_webhook_signature,
    process_signature_webhook_payload,
)
from apps.core.infrastructure.services.signature_whatsapp import maybe_dispatch_signature_whatsapp


class SynplaiSignGatewayHelperTests(SimpleTestCase):
    @override_settings(SYNPLAISIGN_BASE_URL="https://synplaisign.example/")
    def test_build_signing_url(self) -> None:
        self.assertEqual(build_signing_url(token="tok-1"), "https://synplaisign.example/sign/tok-1")

    def test_map_signatories_uses_signature_position_and_zero_based_order(self) -> None:
        mapped = _map_signatories(
            signatory={"name": "Cliente", "email": "a@b.com", "signingOrder": 0},
            fields=[{"pageNumber": 2, "position": {"x": 10.0, "y": 20.0, "width": 30.0, "height": 40.0}}],
        )
        self.assertEqual(mapped[0]["order"], 0)
        self.assertEqual(mapped[0]["deliveryChannel"], "EMAIL")
        self.assertNotIn("phone", mapped[0])
        self.assertEqual(mapped[0]["fieldPage"], 2)
        self.assertEqual(mapped[0]["fieldX"], 10.0)
        self.assertEqual(mapped[0]["fieldY"], 20.0)

    def test_map_signatories_omits_field_coords_for_html(self) -> None:
        mapped = _map_signatories(
            signatory={"name": "Cliente", "email": "a@b.com", "signingOrder": 0},
            fields=[{"pageNumber": 2, "position": {"x": 10.0, "y": 20.0, "width": 30.0, "height": 40.0}}],
            include_field_coords=False,
        )
        self.assertEqual(mapped[0]["order"], 0)
        self.assertNotIn("fieldPage", mapped[0])
        self.assertNotIn("fieldX", mapped[0])
        self.assertNotIn("fieldY", mapped[0])
        self.assertNotIn("fieldWidth", mapped[0])
        self.assertNotIn("fieldHeight", mapped[0])

    def test_map_signatories_sets_both_when_phone_present(self) -> None:
        mapped = _map_signatories(
            signatory={
                "name": "Cliente",
                "email": "a@b.com",
                "phoneNumber": "+5511999999999",
                "signingOrder": 0,
            },
            fields=[],
        )
        self.assertEqual(mapped[0]["phone"], "5511999999999")
        self.assertEqual(mapped[0]["deliveryChannel"], "BOTH")
        self.assertEqual(mapped[0]["order"], 0)

    def test_map_signatories_respects_explicit_delivery_channel(self) -> None:
        mapped = _map_signatories(
            signatory={
                "name": "Cliente",
                "email": "a@b.com",
                "phone": "5511888777666",
                "deliveryChannel": "WHATSAPP",
                "signingOrder": 1,
            },
            fields=[],
        )
        self.assertEqual(mapped[0]["deliveryChannel"], "WHATSAPP")
        self.assertEqual(mapped[0]["phone"], "5511888777666")
        self.assertEqual(mapped[0]["order"], 1)


class SynplaiSignSignatureServiceTests(SimpleTestCase):
    def setUp(self) -> None:
        self.service = SynplaiSignSignatureService()

    @override_settings(SYNPLAISIGN_BASE_URL="https://synplaisign.example")
    @patch("apps.core.infrastructure.services.signature_synplaisign.gateway.send_envelope")
    @patch("apps.core.infrastructure.services.signature_synplaisign.gateway.create_envelope")
    def test_send_document_creates_sends_and_returns_signing_url(
        self,
        create_envelope_mock: Mock,
        send_envelope_mock: Mock,
    ) -> None:
        create_envelope_mock.return_value = SynplaiSignGatewayResult(
            envelope_id="env-1",
            signing_token="tok-abc",
            raw_response={"id": "env-1"},
        )
        send_envelope_mock.return_value = {"message": "ok"}

        result = self.service.send_document(
            SignatureSendRequest(
                document_bytes=b"%PDF",
                file_name="doc.pdf",
                document_ref_id="budget-1",
                title="Orcamento #1",
                message="Assine",
                signatory={"name": "Joao", "email": "joao@example.com", "signingOrder": 0},
                observers=[],
                fields=[{"pageNumber": 1, "position": {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0}}],
                api_key="sk_live_workshop",
                whatsapp_instance="workshop_19",
            )
        )

        self.assertEqual(result.envelope_id, "env-1")
        self.assertEqual(result.document_id, "env-1")
        self.assertEqual(result.provider, "synplaisign")
        self.assertEqual(result.signing_url, "https://synplaisign.example/sign/tok-abc")
        create_envelope_mock.assert_called_once()
        self.assertEqual(create_envelope_mock.call_args.kwargs["api_key"], "sk_live_workshop")
        self.assertEqual(create_envelope_mock.call_args.kwargs["whatsapp_instance"], "workshop_19")
        self.assertEqual(create_envelope_mock.call_args.kwargs["content_type"], "application/pdf")
        signatories = create_envelope_mock.call_args.kwargs["signatories"]
        self.assertEqual(signatories[0]["order"], 0)
        self.assertEqual(signatories[0]["deliveryChannel"], "EMAIL")
        self.assertIn("fieldX", signatories[0])
        send_envelope_mock.assert_called_once_with(api_key="sk_live_workshop", envelope_id="env-1")

    @override_settings(SYNPLAISIGN_BASE_URL="https://synplaisign.example")
    @patch("apps.core.infrastructure.services.signature_synplaisign.gateway.send_envelope")
    @patch("apps.core.infrastructure.services.signature_synplaisign.gateway.create_envelope")
    def test_send_document_html_omits_field_coords(
        self,
        create_envelope_mock: Mock,
        send_envelope_mock: Mock,
    ) -> None:
        create_envelope_mock.return_value = SynplaiSignGatewayResult(
            envelope_id="env-html",
            signing_token="tok-html",
            raw_response={"id": "env-html"},
        )
        send_envelope_mock.return_value = {"message": "ok"}
        html_bytes = b'<div class="signature-block" sign-box></div>'

        result = self.service.send_document(
            SignatureSendRequest(
                document_bytes=html_bytes,
                file_name="orcamento-1.html",
                document_ref_id="budget-1",
                title="Orcamento #1",
                message="Assine",
                signatory={"name": "Joao", "email": "joao@example.com", "signingOrder": 0},
                observers=[],
                fields=[],
                api_key="sk_live_workshop",
                content_type="text/html",
            )
        )

        self.assertEqual(result.envelope_id, "env-html")
        kwargs = create_envelope_mock.call_args.kwargs
        self.assertEqual(kwargs["document_bytes"], html_bytes)
        self.assertEqual(kwargs["content_type"], "text/html")
        self.assertEqual(kwargs["file_name"], "orcamento-1.html")
        signatory = kwargs["signatories"][0]
        self.assertNotIn("fieldX", signatory)
        self.assertNotIn("fieldPage", signatory)

    @patch("apps.core.infrastructure.services.signature_synplaisign.gateway.download_signed_document", return_value=b"%PDF-1.4")
    def test_download_prefers_envelope_id(self, download_mock: Mock) -> None:
        content = self.service.download_signed_document(document_id="doc-old", envelope_id="env-1", api_key="sk_live_workshop")
        self.assertEqual(content, b"%PDF-1.4")
        download_mock.assert_called_once_with(api_key="sk_live_workshop", envelope_id="env-1")

    @patch("apps.core.infrastructure.services.signature_synplaisign.gateway.list_webhooks", return_value=[])
    @patch(
        "apps.core.infrastructure.services.signature_synplaisign.gateway.create_webhook",
        return_value={"id": "wh-1", "url": "https://app/webhook", "secret": "whsec_x"},
    )
    def test_ensure_webhook_creates_when_missing(self, create_mock: Mock, list_mock: Mock) -> None:
        webhook = self.service.ensure_webhook(webhook_url="https://app/webhook", api_key="sk_live_workshop")
        self.assertEqual(webhook["id"], "wh-1")
        create_mock.assert_called_once()
        list_mock.assert_called_once_with(api_key="sk_live_workshop")

    @patch(
        "apps.core.infrastructure.services.signature_synplaisign.gateway.list_webhooks",
        return_value=[{"id": "wh-existing", "url": "https://app/webhook", "events": ["ENVELOPE_COMPLETED"]}],
    )
    @patch("apps.core.infrastructure.services.signature_synplaisign.gateway.create_webhook")
    def test_ensure_webhook_reuses_existing(self, create_mock: Mock, _list_mock: Mock) -> None:
        webhook = self.service.ensure_webhook(webhook_url="https://app/webhook", api_key="sk_live_workshop")
        self.assertEqual(webhook["id"], "wh-existing")
        create_mock.assert_not_called()


class SignatureWhatsAppDispatchTests(SimpleTestCase):
    @patch("apps.core.infrastructure.services.signature_whatsapp.RabbitMQPublisher")
    @patch("apps.core.infrastructure.services.signature_whatsapp.finalize_batch_after_queue")
    @patch("apps.core.infrastructure.services.signature_whatsapp.record_queued_log")
    @patch("apps.core.infrastructure.services.signature_whatsapp.create_dispatch_batch")
    def test_dispatch_queues_when_phone_and_instance_present(
        self,
        create_batch_mock: Mock,
        record_queued_mock: Mock,
        finalize_mock: Mock,
        publisher_cls: Mock,
    ) -> None:
        batch = SimpleNamespace(pk=99)
        create_batch_mock.return_value = batch
        publisher = publisher_cls.return_value

        queued = maybe_dispatch_signature_whatsapp(
            workshop=SimpleNamespace(pk=7, whatsapp_instance_name="workshop_7"),
            customer=SimpleNamespace(pk=3),
            phone="+5511999999999",
            document_title="Orcamento #1",
            signing_url="https://synplaisign.example/sign/tok",
        )

        self.assertTrue(queued)
        publisher.publish_dispatch_item.assert_called_once()
        publisher.publish_workshop_control.assert_called_once_with(7, whatsapp_instance_name="workshop_7")
        record_queued_mock.assert_called_once()
        finalize_mock.assert_called_once()
        publisher.close.assert_called_once()

    def test_dispatch_skipped_without_instance(self) -> None:
        queued = maybe_dispatch_signature_whatsapp(
            workshop=SimpleNamespace(pk=7, whatsapp_instance_name=""),
            customer=SimpleNamespace(pk=3),
            phone="+5511999999999",
            document_title="Orcamento #1",
            signing_url="https://synplaisign.example/sign/tok",
        )
        self.assertFalse(queued)

    @patch("apps.core.infrastructure.services.signature_whatsapp.RabbitMQPublisher")
    @patch("apps.core.infrastructure.services.signature_whatsapp.finalize_batch_after_queue")
    @patch("apps.core.infrastructure.services.signature_whatsapp.record_queue_failure")
    @patch("apps.core.infrastructure.services.signature_whatsapp.create_dispatch_batch")
    def test_dispatch_failure_does_not_raise(
        self,
        create_batch_mock: Mock,
        record_failure_mock: Mock,
        finalize_mock: Mock,
        publisher_cls: Mock,
    ) -> None:
        create_batch_mock.return_value = SimpleNamespace(pk=1)
        publisher = publisher_cls.return_value
        publisher.publish_dispatch_item.side_effect = RuntimeError("broker down")

        queued = maybe_dispatch_signature_whatsapp(
            workshop=SimpleNamespace(pk=7, whatsapp_instance_name="workshop_7"),
            customer=SimpleNamespace(pk=3),
            phone="+5511999999999",
            document_title="Orcamento #1",
            signing_url="https://synplaisign.example/sign/tok",
        )

        self.assertFalse(queued)
        record_failure_mock.assert_called_once()
        finalize_mock.assert_called_once()


class SignatureWebhookHmacTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.view = SignatureWebhookView.as_view()

    @override_settings(SYNPLAISIGN_WEBHOOK_SECRET="whsec_test")
    @patch("apps.core.infrastructure.services.signature_webhook._resolve_workshop_for_envelope", return_value=(None, None, None))
    def test_rejects_invalid_hmac(self, _resolve_mock: Mock) -> None:
        body = json.dumps({"event": "ENVELOPE_COMPLETED", "envelopeId": "env-1"}).encode("utf-8")
        request = self.factory.post(
            "/budget/signature/webhook/",
            data=body,
            content_type="application/json",
            HTTP_X_SYNPLAI_SIGNATURE="sha256=deadbeef",
        )
        response = self.view(request)
        self.assertEqual(response.status_code, 403)

    @override_settings(SYNPLAISIGN_WEBHOOK_SECRET="whsec_test")
    @patch("apps.core.infrastructure.services.signature_webhook._resolve_workshop_for_envelope", return_value=(None, None, None))
    @patch(
        "apps.core.infrastructure.services.signature_webhook.process_signature_webhook_payload",
        return_value=HttpResponse(status=200),
    )
    def test_accepts_valid_hmac(self, process_mock: Mock, _resolve_mock: Mock) -> None:
        body = json.dumps({"event": "ENVELOPE_COMPLETED", "envelopeId": "env-1"}).encode("utf-8")
        signature = build_synplaisign_webhook_signature(body=body, secret="whsec_test")
        request = self.factory.post(
            "/budget/signature/webhook/",
            data=body,
            content_type="application/json",
            HTTP_X_SYNPLAI_SIGNATURE=signature,
        )
        response = self.view(request)
        self.assertEqual(response.status_code, 200)
        process_mock.assert_called_once()


class SignatureWebhookProcessingTests(SimpleTestCase):
    @patch("apps.workorder.models.WorkOrder.objects.filter")
    @patch("apps.budget.models.Budget.objects.filter")
    def test_unknown_envelope_is_acked(self, budget_filter: Mock, workorder_filter: Mock) -> None:
        budget_filter.return_value.first.return_value = None
        budget_filter.return_value.order_by.return_value.values.return_value.__getitem__ = lambda _self, _idx: []
        workorder_filter.return_value.first.return_value = None
        workorder_filter.return_value.order_by.return_value.values.return_value.__getitem__ = lambda _self, _idx: []

        response = process_signature_webhook_payload(
            payload={"event": "ENVELOPE_COMPLETED", "envelopeId": "missing-env"}
        )
        self.assertEqual(response.status_code, 200)

    @patch("apps.workorder.models.WorkOrder.objects.filter")
    @patch("apps.budget.models.Budget.objects.filter")
    def test_non_completed_event_is_ignored(self, budget_filter: Mock, workorder_filter: Mock) -> None:
        budget = SimpleNamespace(pk=1, approve=Mock(return_value=True), mark_signature_approved=Mock())
        budget_filter.return_value.first.return_value = budget
        workorder_filter.return_value.first.return_value = None

        response = process_signature_webhook_payload(
            payload={"event": "DOCUMENT_SIGNED", "envelopeId": "env-1"}
        )
        self.assertEqual(response.status_code, 200)
        budget.approve.assert_not_called()



class BudgetSignatureSendTests(SimpleTestCase):
    @patch("apps.budget.service.get_signature_service")
    @patch("apps.budget.service.render_budget_signature_html_document")
    def test_send_budget_uses_workshop_api_key_without_evolution_dispatch(
        self,
        render_html_mock: Mock,
        get_service_mock: Mock,
    ) -> None:
        from apps.budget.service import send_budget_for_signature

        render_html_mock.return_value = SimpleNamespace(
            content=b'<html><div class="signature-block" sign-box></div></html>',
            content_type="text/html; charset=utf-8",
        )
        service = Mock()
        service.build_signatory_and_observers.return_value = (
            {"name": "Cliente", "email": "c@example.com", "phoneNumber": "+5511988887777", "signingOrder": 0},
            [],
        )
        service.send_document.return_value = SignatureSendResult(
            envelope_id="env-1",
            document_id="env-1",
            provider="synplaisign",
            raw_response={},
            signing_url="https://synplaisign.example/sign/tok",
        )
        get_service_mock.return_value = service

        budget = SimpleNamespace(
            id=1,
            customer=SimpleNamespace(name="Cliente", email="c@example.com", phone="+5511988887777", pk=9),
            workshop=SimpleNamespace(pk=2, whatsapp_instance_name="workshop_2", synplaisign_api_key="sk_live_x"),
            service_expected_completion_at="2026-01-01",
        )

        with patch("apps.budget.service.get_workshop_synplaisign_api_key", return_value="sk_live_x"):
            result = send_budget_for_signature(budget=budget)
        self.assertEqual(result.envelope_id, "env-1")
        send_request = service.send_document.call_args.args[0]
        self.assertEqual(send_request.api_key, "sk_live_x")
        self.assertEqual(send_request.whatsapp_instance, "workshop_2")
        self.assertEqual(send_request.signatory["phoneNumber"], "+5511988887777")
        self.assertEqual(send_request.content_type, "text/html")
        self.assertTrue(send_request.file_name.endswith(".html"))
        self.assertIn(b"sign-box", send_request.document_bytes)
        self.assertEqual(send_request.fields, [])

    def tearDown(self) -> None:
        set_signature_service(SynplaiSignSignatureService())


class SignatureHtmlDocumentTests(SimpleTestCase):
    def test_signature_template_includes_sign_box(self) -> None:
        from django.template.loader import get_template

        template_source = get_template("budget/partials/pdf/visualizarPDF.html").template.source
        self.assertIn("sign-box", template_source)
        self.assertIn("signature-box", template_source)

    @override_settings(SYNPLAISIGN_BASE_URL="https://synplaisign.example")
    @patch("apps.core.infrastructure.gateways.synplaisign.requests.post")
    def test_create_envelope_sends_html_multipart(self, requests_post_mock: Mock) -> None:
        from apps.core.infrastructure.gateways.synplaisign import create_envelope

        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        response.json.return_value = {"id": "env-1", "signatories": [{"token": "tok"}]}
        requests_post_mock.return_value = response

        html = b"<html sign-box></html>"
        create_envelope(
            api_key="sk_live",
            document_bytes=html,
            file_name="doc.html",
            title="T",
            message="M",
            signatories=[{"name": "A", "email": "a@b.com", "order": 0, "deliveryChannel": "EMAIL"}],
            content_type="text/html",
        )

        files = requests_post_mock.call_args.kwargs["files"]
        self.assertEqual(files["file"][0], "doc.html")
        self.assertEqual(files["file"][1], html)
        self.assertEqual(files["file"][2], "text/html")


class SignatureDownloadRouterTests(SimpleTestCase):
    @patch("apps.core.infrastructure.services.signature_download.supersign_gateway.download_signed_document")
    @patch("apps.core.infrastructure.services.signature_download.get_signature_service")
    def test_download_uses_synplaisign_when_successful(
        self,
        get_service_mock: Mock,
        supersign_download_mock: Mock,
    ) -> None:
        from apps.core.infrastructure.services.signature_download import download_signed_pdf

        service = Mock()
        service.download_signed_document.return_value = b"%PDF-syn"
        get_service_mock.return_value = service

        content = download_signed_pdf(
            document_id="env-1",
            envelope_id="env-1",
            synplaisign_api_key="sk_live_workshop",
        )
        self.assertEqual(content, b"%PDF-syn")
        service.download_signed_document.assert_called_once_with(
            document_id="env-1",
            envelope_id="env-1",
            api_key="sk_live_workshop",
        )
        supersign_download_mock.assert_not_called()

    @patch("apps.core.infrastructure.services.signature_download.supersign_gateway.download_signed_document", return_value=b"%PDF-ss")
    @patch("apps.core.infrastructure.services.signature_download.get_signature_service")
    def test_download_falls_back_to_supersign_on_synplaisign_error(
        self,
        get_service_mock: Mock,
        supersign_download_mock: Mock,
    ) -> None:
        from apps.core.domain.contracts.signature import SignatureServiceError
        from apps.core.infrastructure.services.signature_download import download_signed_pdf

        service = Mock()
        service.download_signed_document.side_effect = SignatureServiceError("not found on synplaisign")
        get_service_mock.return_value = service

        content = download_signed_pdf(
            document_id="doc-legacy",
            envelope_id="env-legacy",
            synplaisign_api_key="sk_live_workshop",
        )
        self.assertEqual(content, b"%PDF-ss")
        supersign_download_mock.assert_called_once_with(document_id="doc-legacy")

    @patch("apps.core.infrastructure.services.signature_download.supersign_gateway.download_signed_document")
    @patch("apps.core.infrastructure.services.signature_download.get_signature_service")
    def test_download_raises_when_both_providers_fail(
        self,
        get_service_mock: Mock,
        supersign_download_mock: Mock,
    ) -> None:
        from apps.core.domain.contracts.signature import SignatureServiceError
        from apps.core.infrastructure.gateways.supersign import SuperSignGatewayError
        from apps.core.infrastructure.services.signature_download import download_signed_pdf

        service = Mock()
        service.download_signed_document.side_effect = SignatureServiceError("syn failed")
        get_service_mock.return_value = service
        supersign_download_mock.side_effect = SuperSignGatewayError("ss failed")

        with self.assertRaises(SignatureServiceError):
            download_signed_pdf(
                document_id="doc-1",
                envelope_id="env-1",
                synplaisign_api_key="sk",
            )
