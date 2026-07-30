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
    FiscalDocumentPurpose,
    FiscalDocumentStatus,
    FiscalDocumentType,
    FiscalEmissionAttempt,
    FiscalEmissionAttemptStatus,
    FiscalEmissionOperationType,
    WebmaniaCompany,
    WebmaniaWebhookEvent,
)
from apps.finance.services.nfe_credit import create_and_emit_nfe_credit_type_one
from apps.finance.services.nfe_credit_cancellation import NfeCreditCancellationError, cancel_nfe_credit_document, reconcile_nfe_credit_cancellation
from apps.core.infrastructure.services.webmania.webmania_webhooks import process_webhook_event
from apps.finance.test_nfe_credit import CreditFixtureMixin, _response
from apps.finance.views.nfe_credit import NfeCreditCancellationDownloadView, NfeCreditCancellationPayloadView, NfeCreditCancellationView


class CreditCancellationFixtureMixin(CreditFixtureMixin):
    def emit_credit(self) -> FiscalDocument:
        with patch("apps.finance.services.nfe_credit._build_headers", return_value={}), patch("apps.finance.services.nfe_credit.requests.post", return_value=_response(self.success_payload())):
            return create_and_emit_nfe_credit_type_one(preview=self.preview, workshop=self.workshop, requested_by=self.user, legal_confirmation=True)

    @staticmethod
    def cancellation_payload(*, status: str = "cancelado") -> dict[str, Any]:
        return {
            "status": status,
            "xml": "https://example.test/credit-original.xml",
            "xml_cancelamento": "https://example.test/credit-cancellation.xml",
            "log": {"consumer_secret": "secret"},
        }

    def cancel(self, document: FiscalDocument, **overrides: Any) -> FiscalDocumentEvent:
        kwargs = {"document": document, "reason": "Cancelamento fiscal de credito validado.", "requested_by": self.user, "legal_confirmation": True}
        kwargs.update(overrides)
        with patch("apps.finance.services.nfe_credit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_credit_cancellation.requests.put", return_value=_response(self.cancellation_payload())) as put:
            event = cancel_nfe_credit_document(**kwargs)
        self.put_mock = put
        return event


class FiscalPhaseTwoCreditTypeOneCancellationTests(CreditCancellationFixtureMixin, TestCase):
    def setUp(self) -> None:
        self.preview = self.build_fixture(suffix=74)
        self.document = self.emit_credit()

    def test_authorized_credit_cancellation_contract_and_audit_trail(self) -> None:
        document_count = FiscalDocument.objects.count()
        source = self.preview.basis.source_document
        source_status = source.status
        basis_status = self.preview.basis.status
        preview_status = self.preview.validation_status
        event = self.cancel(self.document)
        payload = self.put_mock.call_args.kwargs["json"]
        self.assertEqual(payload, {"chave": self.document.access_key, "motivo": "Cancelamento fiscal de credito validado."})
        self.assertTrue(self.put_mock.call_args.args[0].endswith("/1/nfe/cancelar/"))
        for forbidden in ("ambiente", "finalidade", "tipo_credito", "produtos", "impostos", "ibs_cbs", "cod_evento", "evento_ibs_cbs", "nfce_referenciada"):
            self.assertNotIn(forbidden, payload)
        self.assertEqual(FiscalDocument.objects.count(), document_count)
        self.assertEqual(event.event_type, FiscalDocumentEventType.CANCELLATION)
        self.assertEqual(event.event_payload_type, "nfe_credit_cancellation")
        self.assertEqual(event.xml_url, self.cancellation_payload()["xml_cancelamento"])
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=event)
        self.assertEqual(attempt.operation_type, FiscalEmissionOperationType.NFE_CREDIT_CANCELLATION)
        self.assertEqual(attempt.request_payload, payload)
        self.document.refresh_from_db()
        source.refresh_from_db()
        self.preview.refresh_from_db()
        self.preview.basis.refresh_from_db()
        self.assertEqual(self.document.status, FiscalDocumentStatus.CANCELED)
        self.assertEqual(source.status, source_status)
        self.assertEqual(self.preview.basis.status, basis_status)
        self.assertEqual(self.preview.validation_status, preview_status)
        self.assertEqual(event.response_payload["log"]["consumer_secret"], "[REDACTED]")

    def test_uuid_is_used_when_access_key_is_absent(self) -> None:
        FiscalDocument.objects.filter(pk=self.document.pk).update(access_key="")
        self.document.refresh_from_db()
        self.cancel(self.document)
        self.assertEqual(self.put_mock.call_args.kwargs["json"], {"uuid": self.document.remote_uuid, "motivo": "Cancelamento fiscal de credito validado."})

    def test_reason_confirmation_and_missing_identifier_are_blocked(self) -> None:
        for reason in ("curto", "x" * 256):
            with self.subTest(reason_length=len(reason)), self.assertRaisesMessage(NfeCreditCancellationError, "15 e 255"):
                self.cancel(self.document, reason=reason)
        with self.assertRaisesMessage(NfeCreditCancellationError, "Confirme"):
            self.cancel(self.document, legal_confirmation=False)
        FiscalDocument.objects.filter(pk=self.document.pk).update(access_key="", remote_uuid="")
        self.document.refresh_from_db()
        with self.assertRaisesMessage(NfeCreditCancellationError, "sem chave ou UUID"):
            self.cancel(self.document)

    def test_ineligible_statuses_and_document_kinds_are_blocked(self) -> None:
        for status in (FiscalDocumentStatus.PROCESSING, FiscalDocumentStatus.REPROVED, FiscalDocumentStatus.UNCERTAIN, FiscalDocumentStatus.CANCELED):
            FiscalDocument.objects.filter(pk=self.document.pk).update(status=status)
            self.document.refresh_from_db()
            with self.subTest(status=status), patch("apps.finance.services.nfe_credit_cancellation.requests.put") as put, self.assertRaises(NfeCreditCancellationError):
                cancel_nfe_credit_document(document=self.document, reason="Cancelamento fiscal de credito validado.", requested_by=self.user, legal_confirmation=True)
            put.assert_not_called()
        FiscalDocument.objects.filter(pk=self.document.pk).update(status=FiscalDocumentStatus.APPROVED, purpose=FiscalDocumentPurpose.NORMAL)
        self.document.refresh_from_db()
        with self.assertRaisesMessage(NfeCreditCancellationError, "somente para NF-e de credito"):
            self.cancel(self.document)
        for purpose in (FiscalDocumentPurpose.RETURN, FiscalDocumentPurpose.REVERSAL, FiscalDocumentPurpose.COMPLEMENTARY, FiscalDocumentPurpose.ADJUSTMENT):
            FiscalDocument.objects.filter(pk=self.document.pk).update(document_type=FiscalDocumentType.NFE, purpose=purpose)
            self.document.refresh_from_db()
            with self.subTest(purpose=purpose), self.assertRaisesMessage(NfeCreditCancellationError, "somente para NF-e de credito"):
                self.cancel(self.document)

    def test_disabled_feature_flag_blocks_before_gateway(self) -> None:
        WebmaniaCompany.objects.filter(workshop=self.workshop).update(credit_debit_basis_enabled=False)
        with patch("apps.finance.services.nfe_credit_cancellation.requests.put") as put, self.assertRaisesMessage(NfeCreditCancellationError, "desabilitado"):
            cancel_nfe_credit_document(document=self.document, reason="Cancelamento fiscal de credito validado.", requested_by=self.user, legal_confirmation=True)
        put.assert_not_called()
        FiscalDocument.objects.filter(pk=self.document.pk).update(purpose=FiscalDocumentPurpose.CREDIT, document_type=FiscalDocumentType.NFCE)
        self.document.refresh_from_db()
        with self.assertRaisesMessage(NfeCreditCancellationError, "somente para NF-e de credito"):
            self.cancel(self.document)

    def test_timeout_marks_event_attempt_uncertain_and_blocks_retry(self) -> None:
        with patch("apps.finance.services.nfe_credit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_credit_cancellation.requests.put", side_effect=requests.Timeout), self.assertRaisesMessage(NfeCreditCancellationError, "incerto"):
            cancel_nfe_credit_document(document=self.document, reason="Cancelamento fiscal de credito validado.", requested_by=self.user, legal_confirmation=True)
        event = self.document.events.get(event_type=FiscalDocumentEventType.CANCELLATION)
        self.assertEqual(event.status, FiscalDocumentEventStatus.UNCERTAIN)
        self.assertEqual(event.emission_attempts.get().status, FiscalEmissionAttemptStatus.UNCERTAIN)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, FiscalDocumentStatus.APPROVED)
        with patch("apps.finance.services.nfe_credit_cancellation.requests.put") as put, self.assertRaisesMessage(NfeCreditCancellationError, "estado incerto"):
            cancel_nfe_credit_document(document=self.document, reason="Outro cancelamento fiscal validado.", requested_by=self.user, legal_confirmation=True)
        put.assert_not_called()

    def test_rejected_response_with_xml_does_not_cancel_document(self) -> None:
        response = self.cancellation_payload(status="rejeitado")
        with patch("apps.finance.services.nfe_credit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_credit_cancellation.requests.put", return_value=_response(response)), self.assertRaises(NfeCreditCancellationError):
            cancel_nfe_credit_document(document=self.document, reason="Cancelamento fiscal de credito validado.", requested_by=self.user, legal_confirmation=True)
        event = self.document.events.get()
        self.assertEqual(event.status, FiscalDocumentEventStatus.FAILED)
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, FiscalDocumentStatus.APPROVED)

    def test_webhook_updates_only_credit_and_is_idempotent(self) -> None:
        with patch("apps.finance.services.nfe_credit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_credit_cancellation.requests.put", side_effect=requests.Timeout), self.assertRaises(NfeCreditCancellationError):
            cancel_nfe_credit_document(document=self.document, reason="Cancelamento fiscal de credito validado.", requested_by=self.user, legal_confirmation=True)
        event = self.document.events.get()
        source = self.preview.basis.source_document
        payload = {**self.cancellation_payload(), "modelo": "nfe", "uuid": self.document.remote_uuid, "chave": self.document.access_key}
        webhook = WebmaniaWebhookEvent.objects.create(model="nfe", event_uuid=self.document.remote_uuid, fingerprint="credit-cancel-webhook", payload=payload)
        self.assertTrue(process_webhook_event(webhook))
        self.assertTrue(process_webhook_event(webhook))
        event.refresh_from_db()
        self.document.refresh_from_db()
        source.refresh_from_db()
        self.assertEqual(event.status, FiscalDocumentEventStatus.SUCCEEDED)
        self.assertEqual(self.document.status, FiscalDocumentStatus.CANCELED)
        self.assertEqual(source.status, FiscalDocumentStatus.APPROVED)

    def test_ambiguous_webhook_does_not_update_any_credit(self) -> None:
        with patch("apps.finance.services.nfe_credit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_credit_cancellation.requests.put", side_effect=requests.Timeout), self.assertRaises(NfeCreditCancellationError):
            cancel_nfe_credit_document(document=self.document, reason="Cancelamento fiscal de credito validado.", requested_by=self.user, legal_confirmation=True)
        first_document = self.document
        second_preview = self.build_fixture(suffix=77)
        self.preview = second_preview
        second_document = self.emit_credit()
        with patch("apps.finance.services.nfe_credit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_credit_cancellation.requests.put", side_effect=requests.Timeout), self.assertRaises(NfeCreditCancellationError):
            cancel_nfe_credit_document(document=second_document, reason="Cancelamento fiscal de credito validado.", requested_by=self.user, legal_confirmation=True)
        payload = {**self.cancellation_payload(), "modelo": "nfe", "uuid": first_document.remote_uuid}
        webhook = WebmaniaWebhookEvent.objects.create(model="nfe", event_uuid=first_document.remote_uuid, fingerprint="credit-cancel-ambiguous", payload=payload)
        self.assertFalse(process_webhook_event(webhook))
        first_document.refresh_from_db()
        second_document.refresh_from_db()
        self.assertEqual(first_document.status, FiscalDocumentStatus.APPROVED)
        self.assertEqual(second_document.status, FiscalDocumentStatus.APPROVED)
        self.assertEqual(second_preview.credit_document.pk, second_document.pk)

    def test_reconciliation_queries_without_reissuing_or_mutating_source(self) -> None:
        with patch("apps.finance.services.nfe_credit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_credit_cancellation.requests.put", side_effect=requests.Timeout), self.assertRaises(NfeCreditCancellationError):
            cancel_nfe_credit_document(document=self.document, reason="Cancelamento fiscal de credito validado.", requested_by=self.user, legal_confirmation=True)
        event = self.document.events.get()
        source = self.preview.basis.source_document
        with patch("apps.finance.services.nfe_credit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_credit_cancellation.requests.get", return_value=_response(self.cancellation_payload())) as get, patch("apps.finance.services.nfe_credit_cancellation.requests.put") as put:
            reconciled = reconcile_nfe_credit_cancellation(event=event)
        self.assertEqual(reconciled.status, FiscalDocumentEventStatus.SUCCEEDED)
        get.assert_called_once()
        put.assert_not_called()
        source.refresh_from_db()
        self.assertEqual(source.status, FiscalDocumentStatus.APPROVED)

    def test_permission_and_cross_workshop_are_blocked_before_gateway(self) -> None:
        request = RequestFactory().post("/", {"reason": "Cancelamento fiscal de credito validado.", "legal_confirmation": "on"})
        request.user = self.user
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=False), patch("apps.finance.views.nfe_credit.cancel_nfe_credit_document") as service, self.assertRaises(PermissionDenied):
            NfeCreditCancellationView.as_view()(request, pk=self.document.pk)
        service.assert_not_called()
        _other_preview = self.build_fixture(suffix=75)
        request.user = self.user
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=True), self.assertRaises(Http404):
            NfeCreditCancellationView.as_view()(request, pk=self.document.pk)

    def test_cancellation_payload_and_download_views_require_specific_permissions(self) -> None:
        event = self.cancel(self.document)
        request = RequestFactory().get("/")
        request.user = self.user
        for view in (NfeCreditCancellationPayloadView, NfeCreditCancellationDownloadView):
            with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=False), self.assertRaises(PermissionDenied):
                view.as_view()(request, pk=self.document.pk, event_pk=event.pk)


class FiscalPhaseTwoCreditTypeOneCancellationConcurrentTests(CreditCancellationFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def setUp(self) -> None:
        self.preview = self.build_fixture(suffix=76)
        self.document = self.emit_credit()

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
                cancel_nfe_credit_document(document=document, reason="Cancelamento fiscal de credito validado.", requested_by=user, legal_confirmation=True)
            except Exception as exc:
                with result_lock:
                    errors.append(str(exc))
            else:
                with result_lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with patch("apps.finance.services.nfe_credit_cancellation._build_headers", return_value={}), patch("apps.finance.services.nfe_credit_cancellation.requests.put", side_effect=delayed) as put:
            threads = [threading.Thread(target=run), threading.Thread(target=run)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)
        self.assertEqual(put.call_count, 1, errors)
        self.assertEqual(results, ["sent"], errors)
        self.assertEqual(len(errors), 1)
        self.assertEqual(FiscalDocumentEvent.objects.filter(document=self.document, event_payload_type="nfe_credit_cancellation").count(), 1)
