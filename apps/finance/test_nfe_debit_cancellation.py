from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import Mock, patch

import requests
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections
from django.http import Http404
from django.test import RequestFactory, TestCase, TransactionTestCase

from apps.accounts.models import User
from apps.finance.models.finance import (
    FiscalDocument,
    FiscalDocumentEvent,
    FiscalDocumentEventStatus,
    FiscalDocumentEventType,
    FiscalDocumentOrigin,
    FiscalDocumentPurpose,
    FiscalDocumentStatus,
    FiscalDocumentType,
    FiscalEmissionAttemptStatus,
    FiscalEmissionOperationType,
    WebmaniaCompany,
    WebmaniaWebhookEvent,
)
from apps.finance.services.nfe_debit import create_and_emit_nfe_debit_type_four
from apps.finance.services.nfe_debit_cancellation import NfeDebitCancellationError, cancel_nfe_debit_document, reconcile_nfe_debit_cancellation
from apps.core.infrastructure.services.webmania.webmania_documents import DownloadedWebmaniaDocument
from apps.core.infrastructure.services.webmania.webmania_webhooks import process_webhook_event
from apps.finance.test_nfe_debit import DebitFixtureMixin, _response
from apps.finance.views.nfe_debit import NfeDebitCancellationDownloadView, NfeDebitCancellationPayloadView, NfeDebitCancellationView


class DebitCancellationFixtureMixin(DebitFixtureMixin):
    def emit_debit(self) -> FiscalDocument:
        with patch("apps.finance.services.nfe_debit._build_headers", return_value={}), patch("apps.finance.services.nfe_debit.requests.post", return_value=_response(self.success_payload())):
            return create_and_emit_nfe_debit_type_four(preview=self.preview, workshop=self.workshop, requested_by=self.user, legal_confirmation=True)

    def cancellation_payload(self, *, status: str = "cancelado") -> dict[str, Any]:
        return {"uuid": self.document.remote_uuid, "chave": self.document.access_key, "modelo": "nfe", "status": status, "xml": "https://example.test/debit-original.xml", "xml_cancelamento": "https://example.test/debit-cancel.xml", "log": {"consumer_secret": "secret"}}

    def cancel(self, **overrides: Any) -> FiscalDocumentEvent:
        kwargs = {"document": self.document, "reason": "Cancelamento fiscal de débito validado.", "requested_by": self.user, "legal_confirmation": True}
        kwargs.update(overrides)
        with patch("apps.finance.services.nfe_debit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_debit_cancellation.requests.put", return_value=_response(self.cancellation_payload())) as put:
            event = cancel_nfe_debit_document(**kwargs)
        self.put_mock = put
        return event


class FiscalPhaseTwoDebitTypeFourCancellationTests(DebitCancellationFixtureMixin, TestCase):
    def setUp(self) -> None:
        self.preview = self.build_fixture(suffix=87)
        self.document = self.emit_debit()

    def test_contract_audit_trail_and_source_immutability(self) -> None:
        source = self.preview.basis.source_document
        source_status = source.status
        basis_status = self.preview.basis.status
        preview_payload = dict(self.preview.product_payload)
        document_count = FiscalDocument.objects.count()

        event = self.cancel()

        payload = self.put_mock.call_args.kwargs["json"]
        self.assertTrue(self.put_mock.call_args.args[0].endswith("/1/nfe/cancelar/"))
        self.assertEqual(payload, {"chave": self.document.access_key, "motivo": "Cancelamento fiscal de débito validado."})
        self.assertFalse({"ambiente", "finalidade", "tipo_debito", "dfe_referenciado", "produtos", "impostos", "ibs_cbs", "cod_evento", "nfce_referenciada"}.intersection(payload))
        self.assertEqual(event.event_type, FiscalDocumentEventType.CANCELLATION)
        self.assertEqual(event.event_payload_type, "nfe_debit_cancellation")
        self.assertEqual(event.status, FiscalDocumentEventStatus.SUCCEEDED)
        self.assertEqual(event.xml_url, "https://example.test/debit-cancel.xml")
        attempt = event.emission_attempts.get()
        self.assertEqual(attempt.operation_type, FiscalEmissionOperationType.NFE_DEBIT_CANCELLATION)
        self.assertEqual(attempt.request_payload, payload)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(FiscalDocument.objects.count(), document_count)
        self.document.refresh_from_db()
        source.refresh_from_db()
        self.preview.refresh_from_db()
        self.preview.basis.refresh_from_db()
        self.assertEqual(self.document.status, FiscalDocumentStatus.CANCELED)
        self.assertEqual(source.status, source_status)
        self.assertEqual(self.preview.basis.status, basis_status)
        self.assertEqual(self.preview.product_payload, preview_payload)
        self.assertNotEqual(event.response_payload["log"]["consumer_secret"], "secret")
        self.assertEqual(event.response_payload["log"]["consumer_secret"], "[REDACTED]")

    def test_reason_confirmation_identifier_and_ineligible_documents_are_blocked(self) -> None:
        for reason in ("curto", "x" * 256):
            with self.subTest(reason_length=len(reason)), patch("apps.finance.services.nfe_debit_cancellation.requests.put") as put, self.assertRaises(NfeDebitCancellationError):
                cancel_nfe_debit_document(document=self.document, reason=reason, requested_by=self.user, legal_confirmation=True)
            put.assert_not_called()
        with patch("apps.finance.services.nfe_debit_cancellation.requests.put") as put, self.assertRaisesMessage(NfeDebitCancellationError, "Confirme"):
            cancel_nfe_debit_document(document=self.document, reason="Cancelamento fiscal de débito validado.", requested_by=self.user, legal_confirmation=False)
        put.assert_not_called()

        for status in [FiscalDocumentStatus.PROCESSING, FiscalDocumentStatus.REPROVED, FiscalDocumentStatus.DENIED, FiscalDocumentStatus.UNCERTAIN, FiscalDocumentStatus.CANCELED]:
            FiscalDocument.objects.filter(pk=self.document.pk).update(status=status)
            self.document.refresh_from_db()
            with self.subTest(status=status), patch("apps.finance.services.nfe_debit_cancellation.requests.put") as put, self.assertRaises(NfeDebitCancellationError):
                cancel_nfe_debit_document(document=self.document, reason="Cancelamento fiscal de débito validado.", requested_by=self.user, legal_confirmation=True)
            put.assert_not_called()

        FiscalDocument.objects.filter(pk=self.document.pk).update(status=FiscalDocumentStatus.APPROVED, remote_uuid="", access_key="")
        self.document.refresh_from_db()
        with patch("apps.finance.services.nfe_debit_cancellation.requests.put") as put, self.assertRaisesMessage(NfeDebitCancellationError, "sem chave ou UUID"):
            cancel_nfe_debit_document(document=self.document, reason="Cancelamento fiscal de débito validado.", requested_by=self.user, legal_confirmation=True)
        put.assert_not_called()

    def test_non_debit_documents_and_disabled_feature_are_blocked(self) -> None:
        original_purpose = self.document.purpose
        for document_type, purpose, fiscal_type in [
            (FiscalDocumentType.NFE, FiscalDocumentPurpose.RETURN, ""),
            (FiscalDocumentType.NFE, FiscalDocumentPurpose.NORMAL, ""),
            (FiscalDocumentType.NFCE, FiscalDocumentPurpose.NORMAL, ""),
        ]:
            FiscalDocument.objects.filter(pk=self.document.pk).update(document_type=document_type, purpose=purpose, fiscal_purpose_type=fiscal_type)
            self.document.refresh_from_db()
            with self.subTest(document_type=document_type, purpose=purpose), patch("apps.finance.services.nfe_debit_cancellation.requests.put") as put, self.assertRaises(NfeDebitCancellationError):
                cancel_nfe_debit_document(document=self.document, reason="Cancelamento fiscal de débito validado.", requested_by=self.user, legal_confirmation=True)
            put.assert_not_called()
        FiscalDocument.objects.filter(pk=self.document.pk).update(document_type=FiscalDocumentType.NFE, purpose=original_purpose, fiscal_purpose_type="4")
        WebmaniaCompany.objects.filter(workshop=self.workshop).update(nfe_debit_emission_enabled=False)
        self.document.refresh_from_db()
        with patch("apps.finance.services.nfe_debit_cancellation.requests.put") as put, self.assertRaisesMessage(NfeDebitCancellationError, "desabilitada"):
            cancel_nfe_debit_document(document=self.document, reason="Cancelamento fiscal de débito validado.", requested_by=self.user, legal_confirmation=True)
        put.assert_not_called()

    def test_timeout_is_uncertain_and_blocks_retry_with_frozen_payload(self) -> None:
        with patch("apps.finance.services.nfe_debit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_debit_cancellation.requests.put", side_effect=requests.Timeout), self.assertRaisesMessage(NfeDebitCancellationError, "incerto"):
            cancel_nfe_debit_document(document=self.document, reason="Cancelamento fiscal de débito validado.", requested_by=self.user, legal_confirmation=True)
        event = self.document.events.get(event_payload_type="nfe_debit_cancellation")
        attempt = event.emission_attempts.get()
        self.assertEqual(event.status, FiscalDocumentEventStatus.UNCERTAIN)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.UNCERTAIN)
        self.assertEqual(attempt.request_payload, event.request_payload)
        with patch("apps.finance.services.nfe_debit_cancellation.requests.put") as put, self.assertRaisesMessage(NfeDebitCancellationError, "estado incerto"):
            cancel_nfe_debit_document(document=self.document, reason="Outro cancelamento fiscal validado.", requested_by=self.user, legal_confirmation=True)
        put.assert_not_called()
        self.assertEqual(self.document.events.filter(event_payload_type="nfe_debit_cancellation").count(), 1)

    def test_rejected_or_processing_response_does_not_cancel_document(self) -> None:
        for status, expected_event_status in [("reprovado", FiscalDocumentEventStatus.FAILED), ("processando", FiscalDocumentEventStatus.UNCERTAIN)]:
            preview = self.build_fixture(suffix=88 if status == "reprovado" else 89)
            self.preview = preview
            self.document = self.emit_debit()
            payload = self.cancellation_payload(status=status)
            payload.pop("uuid")
            with patch("apps.finance.services.nfe_debit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_debit_cancellation.requests.put", return_value=_response(payload)), self.assertRaises(NfeDebitCancellationError):
                cancel_nfe_debit_document(document=self.document, reason="Cancelamento fiscal de débito validado.", requested_by=self.user, legal_confirmation=True)
            event = self.document.events.get(event_payload_type="nfe_debit_cancellation")
            self.document.refresh_from_db()
            self.assertEqual(event.status, expected_event_status)
            self.assertEqual(self.document.status, FiscalDocumentStatus.APPROVED)

    def test_webhook_is_idempotent_and_updates_only_debit_document(self) -> None:
        with patch("apps.finance.services.nfe_debit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_debit_cancellation.requests.put", side_effect=requests.Timeout), self.assertRaises(NfeDebitCancellationError):
            cancel_nfe_debit_document(document=self.document, reason="Cancelamento fiscal de débito validado.", requested_by=self.user, legal_confirmation=True)
        event = self.document.events.get(event_payload_type="nfe_debit_cancellation")
        source = self.preview.basis.source_document
        payload = self.cancellation_payload()
        webhook = WebmaniaWebhookEvent.objects.create(model="nfe", event_uuid=self.document.remote_uuid, fingerprint="debit-cancel-webhook", payload=payload)
        self.assertTrue(process_webhook_event(webhook))
        self.assertTrue(process_webhook_event(webhook))
        event.refresh_from_db()
        self.document.refresh_from_db()
        source.refresh_from_db()
        self.assertEqual(event.status, FiscalDocumentEventStatus.SUCCEEDED)
        self.assertEqual(self.document.status, FiscalDocumentStatus.CANCELED)
        self.assertEqual(source.status, FiscalDocumentStatus.APPROVED)

    def test_ambiguous_credit_and_debit_cancellations_update_neither(self) -> None:
        with patch("apps.finance.services.nfe_debit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_debit_cancellation.requests.put", side_effect=requests.Timeout), self.assertRaises(NfeDebitCancellationError):
            cancel_nfe_debit_document(document=self.document, reason="Cancelamento fiscal de débito validado.", requested_by=self.user, legal_confirmation=True)
        debit_event = self.document.events.get(event_payload_type="nfe_debit_cancellation")
        debit_workshop = self.workshop
        other_preview = self.build_fixture(suffix=90)
        credit_document = FiscalDocument.objects.create(workshop=other_preview.workshop, account=other_preview.workshop.account, document_type=FiscalDocumentType.NFE, origin=FiscalDocumentOrigin.LOCAL, purpose=FiscalDocumentPurpose.NORMAL, fiscal_purpose_type="", remote_uuid=self.document.remote_uuid, access_key=self.document.access_key, status=FiscalDocumentStatus.APPROVED)
        credit_event = FiscalDocumentEvent.objects.create(document=credit_document, event_type=FiscalDocumentEventType.CANCELLATION, event_sequence=1, event_payload_type="nfe_credit_cancellation", status=FiscalDocumentEventStatus.UNCERTAIN, remote_model="nfe")
        payload = self.cancellation_payload()
        webhook = WebmaniaWebhookEvent.objects.create(model="nfe", event_uuid=self.document.remote_uuid, fingerprint="debit-credit-cancel-ambiguous", payload=payload)
        self.assertFalse(process_webhook_event(webhook))
        debit_event.refresh_from_db()
        credit_event.refresh_from_db()
        self.assertNotEqual(debit_workshop.pk, credit_document.workshop_id)
        self.assertEqual(debit_event.status, FiscalDocumentEventStatus.UNCERTAIN)
        self.assertEqual(credit_event.status, FiscalDocumentEventStatus.UNCERTAIN)

    def test_reconciliation_queries_without_reissuing_or_mutating_source(self) -> None:
        with patch("apps.finance.services.nfe_debit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_debit_cancellation.requests.put", side_effect=requests.Timeout), self.assertRaises(NfeDebitCancellationError):
            cancel_nfe_debit_document(document=self.document, reason="Cancelamento fiscal de débito validado.", requested_by=self.user, legal_confirmation=True)
        event = self.document.events.get(event_payload_type="nfe_debit_cancellation")
        source = self.preview.basis.source_document
        with patch("apps.finance.services.nfe_debit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_debit_cancellation.requests.get", return_value=_response(self.cancellation_payload())) as get, patch("apps.finance.services.nfe_debit_cancellation.requests.put") as put:
            reconciled = reconcile_nfe_debit_cancellation(event=event)
        self.assertEqual(reconciled.status, FiscalDocumentEventStatus.SUCCEEDED)
        get.assert_called_once()
        put.assert_not_called()
        source.refresh_from_db()
        self.assertEqual(source.status, FiscalDocumentStatus.APPROVED)

    def test_permission_cross_workshop_payload_and_download_are_protected(self) -> None:
        request = RequestFactory().post("/", {"reason": "Cancelamento fiscal de débito validado.", "legal_confirmation": "on"})
        request.user = self.user
        def issue_only(*args: Any, **kwargs: Any) -> bool:
            return kwargs.get("codename") == "issue_nfe_debit"

        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", side_effect=issue_only), patch("apps.finance.views.nfe_debit.cancel_nfe_debit_document") as service, self.assertRaises(PermissionDenied):
            NfeDebitCancellationView.as_view()(request, pk=self.document.pk)
        service.assert_not_called()
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=False), patch("apps.finance.views.nfe_debit.cancel_nfe_debit_document") as service, self.assertRaises(PermissionDenied):
            NfeDebitCancellationView.as_view()(request, pk=self.document.pk)
        service.assert_not_called()

        event = self.cancel()
        get_request = RequestFactory().get("/")
        get_request.user = self.user
        for view in (NfeDebitCancellationPayloadView, NfeDebitCancellationDownloadView):
            with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=False), self.assertRaises(PermissionDenied):
                view.as_view()(get_request, pk=self.document.pk, event_pk=event.pk)
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=True):
            payload_response = NfeDebitCancellationPayloadView.as_view()(get_request, pk=self.document.pk, event_pk=event.pk)
        self.assertNotIn('"consumer_secret": "secret"', payload_response.content.decode())
        self.assertIn("[REDACTED]", payload_response.content.decode())
        downloaded = DownloadedWebmaniaDocument(content=b"xml", content_type="application/xml", content_disposition="")
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=True), patch("apps.finance.views.nfe_debit.download_webmania_document", return_value=downloaded):
            response = NfeDebitCancellationDownloadView.as_view()(get_request, pk=self.document.pk, event_pk=event.pk)
        self.assertEqual(response.content, b"xml")

        original_document = self.document
        self.build_fixture(suffix=91)
        get_request.user = self.user
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=True), self.assertRaises(Http404):
            NfeDebitCancellationPayloadView.as_view()(get_request, pk=original_document.pk, event_pk=event.pk)


class FiscalPhaseTwoDebitTypeFourCancellationConcurrentTests(DebitCancellationFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def setUp(self) -> None:
        self.preview = self.build_fixture(suffix=92)
        self.document = self.emit_debit()

    def test_concurrent_same_cancellation_calls_remote_once(self) -> None:
        barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[str] = []
        result_lock = threading.Lock()

        def delayed(*args: Any, **kwargs: Any) -> Mock:
            time.sleep(0.1)
            return _response(self.cancellation_payload())

        def run() -> None:
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                document = FiscalDocument.objects.get(pk=self.document.pk)
                user = User.objects.get(pk=self.user.pk)
                cancel_nfe_debit_document(document=document, reason="Cancelamento fiscal de débito validado.", requested_by=user, legal_confirmation=True)
            except Exception as exc:
                with result_lock:
                    errors.append(str(exc))
            else:
                with result_lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with patch("apps.finance.services.nfe_debit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_debit_cancellation.requests.put", side_effect=delayed) as put:
            threads = [threading.Thread(target=run), threading.Thread(target=run)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)
        self.assertEqual(put.call_count, 1, errors)
        self.assertEqual(results, ["sent"], errors)
        self.assertEqual(len(errors), 1)
        self.assertEqual(FiscalDocumentEvent.objects.filter(document=self.document, event_payload_type="nfe_debit_cancellation").count(), 1)
