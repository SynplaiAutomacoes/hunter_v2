from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import requests
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.http import Http404
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.models import Account, User
from apps.budget.models import Budget
from apps.finance.models.finance import (
    FiscalDocumentEvent,
    FiscalDocumentEventStatus,
    FiscalEmissionAttempt,
    FiscalEmissionAttemptStatus,
    NfeItem,
    NfeRequest,
    NfseItem,
    NfseRequest,
    WebmaniaWebhookEvent,
)
from apps.finance.services.nfe_events import NfeCorrectionError, emit_nfe_correction, reconcile_cce_event, validate_correction_text
from apps.finance.views.nfe import NfeCorrectionDownloadView, NfeCorrectionIssueView, NfeRequestDetailView
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


CORRECTION_TEXT = "Corrigir informacao complementar sobre a embalagem utilizada."


def _mock_response(payload: dict[str, object]) -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


class NfeCorrectionOperationalTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta CC-e")
        self.workshop = self._create_workshop(suffix=10)
        self.other_workshop = self._create_workshop(suffix=11)
        self.user = User.objects.create_user(username="fiscal-cce", password="test", cpf="98765432100")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.item = self._create_nfe_item(workshop=self.workshop, suffix=10)

    def _create_workshop(self, *, suffix: int) -> Workshop:
        return Workshop.objects.create(
            account=self.account,
            name=f"Oficina CC-e {suffix}",
            cnpj=f"12.345.678/0001-{suffix:02d}",
            phone=f"+5511999999{suffix:03d}",
            address=f"Rua CC-e, {suffix}",
        )

    def _create_nfe_item(self, *, workshop: Workshop, suffix: int, access_key: str | None = None) -> NfeItem:
        budget = Budget.objects.create(workshop=workshop, entry_date=timezone.localdate())
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=workshop, workorder=workorder, tax_class="REFNFE")
        return NfeItem.objects.create(
            workshop=workshop,
            workorder=workorder,
            request=nfe_request,
            uuid=uuid4(),
            status="aprovado",
            access_key=access_key or f"35{suffix:042d}"[-44:],
            number=str(1000 + suffix),
            series="1",
            xml_url=f"https://example.test/nfe-{suffix}.xml",
        )

    def _emit_success(
        self,
        *,
        item: NfeItem | None = None,
        status: str = "aprovado",
        remote_uuid: str | None = None,
        event_sequence: int = 1,
        protocol: str = "135260000000001",
    ) -> FiscalDocumentEvent:
        payload = {
            "uuid": remote_uuid or str(uuid4()),
            "modelo": "cce",
            "status": status,
            "evento": event_sequence,
            "protocolo": protocol,
            "motivo": "Evento de carta de correcao registrado",
            "xml": "https://example.test/cce.xml",
            "dacce": "https://example.test/dacce.pdf",
            "log": {"authorization": "secret"},
        }
        with (
            patch("apps.finance.services.nfe_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_events.requests.post", return_value=_mock_response(payload)),
        ):
            return emit_nfe_correction(nfe_item=item or self.item, correction_text=CORRECTION_TEXT, requested_by=self.user)

    def _emit_timeout(self, *, item: NfeItem | None = None) -> FiscalDocumentEvent:
        with (
            patch("apps.finance.services.nfe_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_events.requests.post", side_effect=requests.Timeout("timeout")),
        ):
            with self.assertRaisesMessage(NfeCorrectionError, "estado remoto incerto"):
                emit_nfe_correction(nfe_item=item or self.item, correction_text=CORRECTION_TEXT, requested_by=self.user)
        return FiscalDocumentEvent.objects.get(document__legacy_nfe_item=item or self.item)

    def test_emission_success_preserves_original_nfe_and_separates_event_artifacts(self) -> None:
        original_xml = self.item.xml_url

        event = self._emit_success()
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=event)

        self.assertEqual(event.status, FiscalDocumentEventStatus.APPROVED)
        self.assertEqual(event.event_sequence, 1)
        self.assertEqual(event.remote_event_id, "135260000000001")
        self.assertEqual(event.xml_url, "https://example.test/cce.xml")
        self.assertEqual(event.dacce_url, "https://example.test/dacce.pdf")
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(event.response_payload["log"]["authorization"], "[REDACTED]")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "aprovado")
        self.assertEqual(self.item.xml_url, original_xml)

    def test_official_request_and_response_contract_is_preserved_in_existing_event(self) -> None:
        remote_uuid = str(uuid4())
        response_payload = {
            "uuid": remote_uuid,
            "status": "aprovado",
            "evento": "1",
            "modelo": "cce",
            "protocolo_evento": "135260000000999",
            "xml": "https://example.test/official-cce.xml",
            "dacce": "https://example.test/official-dacce.pdf",
            "log": {"codigo": "135", "mensagem": "Evento registrado"},
        }
        with (
            patch("apps.finance.services.nfe_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_events.requests.post", return_value=_mock_response(response_payload)) as post_mock,
        ):
            event = emit_nfe_correction(nfe_item=self.item, correction_text=CORRECTION_TEXT, requested_by=self.user)

        sent_payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(
            {key: sent_payload[key] for key in ("correcao", "ambiente", "evento", "chave")},
            {
                "correcao": CORRECTION_TEXT,
                "ambiente": 2,
                "evento": 1,
                "chave": self.item.access_key,
            },
        )
        self.assertTrue(str(sent_payload["url_notificacao"]).startswith("http://localhost:8000/finance/webmania/webhook/"))
        self.assertEqual(event.remote_uuid, remote_uuid)
        self.assertEqual(event.remote_event_id, "135260000000999")
        self.assertEqual(event.xml_url, response_payload["xml"])
        self.assertEqual(event.dacce_url, response_payload["dacce"])
        self.assertEqual(event.response_payload["log"], response_payload["log"])
        self.assertEqual(event.document.legacy_nfe_item_id, self.item.pk)

    def test_rejected_response_fails_attempt_without_changing_original_nfe(self) -> None:
        payload = {"uuid": str(uuid4()), "modelo": "cce", "status": "reprovado", "evento": 1, "motivo": "Rejeicao do evento"}
        with (
            patch("apps.finance.services.nfe_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_events.requests.post", return_value=_mock_response(payload)),
        ):
            with self.assertRaisesMessage(NfeCorrectionError, "Carta de correção rejeitada"):
                emit_nfe_correction(nfe_item=self.item, correction_text=CORRECTION_TEXT, requested_by=self.user)

        event = FiscalDocumentEvent.objects.get(document__legacy_nfe_item=self.item)
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=event)
        self.assertEqual(event.status, FiscalDocumentEventStatus.REPROVED)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.FAILED)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "aprovado")

    def test_success_response_with_invalid_uuid_remains_uncertain(self) -> None:
        payload = {"uuid": "uuid-invalido", "modelo": "cce", "status": "aprovado", "evento": 1}
        with (
            patch("apps.finance.services.nfe_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_events.requests.post", return_value=_mock_response(payload)) as post_mock,
        ):
            with self.assertRaisesMessage(NfeCorrectionError, "estado remoto incerto"):
                emit_nfe_correction(nfe_item=self.item, correction_text=CORRECTION_TEXT, requested_by=self.user)

        event = FiscalDocumentEvent.objects.get(document__legacy_nfe_item=self.item)
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=event)
        post_mock.assert_called_once()
        self.assertEqual(event.status, FiscalDocumentEventStatus.UNCERTAIN)
        self.assertEqual(event.response_payload["uuid"], "uuid-invalido")
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.UNCERTAIN)

    def test_timeout_is_uncertain_and_manual_duplicate_does_not_resend(self) -> None:
        with (
            patch("apps.finance.services.nfe_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_events.requests.post", side_effect=requests.Timeout("timeout")) as post_mock,
        ):
            with self.assertRaisesMessage(NfeCorrectionError, "estado remoto incerto"):
                emit_nfe_correction(nfe_item=self.item, correction_text=CORRECTION_TEXT, requested_by=self.user)
            with self.assertRaisesMessage(NfeCorrectionError, "estado incerto"):
                emit_nfe_correction(nfe_item=self.item, correction_text=CORRECTION_TEXT, requested_by=self.user)

        event = FiscalDocumentEvent.objects.get(document__legacy_nfe_item=self.item)
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=event)
        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(event.status, FiscalDocumentEventStatus.UNCERTAIN)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.UNCERTAIN)
        self.assertEqual(event.event_sequence, 1)

    def test_validation_rejects_changes_to_protected_fiscal_data_before_post(self) -> None:
        with patch("apps.finance.services.nfe_events.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeCorrectionError, "não pode alterar valores"):
                validate_correction_text("Alterar o valor total da nota fiscal emitida.")

        post_mock.assert_not_called()
        self.assertFalse(FiscalDocumentEvent.objects.exists())

    def test_webhook_resolves_uncertain_event_and_attempt_idempotently(self) -> None:
        from apps.core.infrastructure.services.webmania.webmania_webhooks import process_pending_webhook_events, store_webhook_event

        event = self._emit_timeout()
        remote_uuid = str(uuid4())
        payload = {
            "modelo": "cce",
            "uuid": remote_uuid,
            "status": "aprovado",
            "chave": self.item.access_key,
            "evento": 1,
            "protocolo": "135260000000002",
            "xml": "https://example.test/webhook-cce.xml",
            "dacce": "https://example.test/webhook-dacce.pdf",
        }
        webhook = store_webhook_event(payload=payload)
        duplicate = store_webhook_event(payload=payload)

        self.assertEqual(webhook.pk, duplicate.pk)
        self.assertEqual(process_pending_webhook_events(model="cce", event_uuid=remote_uuid), 1)
        self.assertEqual(process_pending_webhook_events(model="cce", event_uuid=remote_uuid), 0)
        event.refresh_from_db()
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=event)
        self.assertEqual(event.status, FiscalDocumentEventStatus.APPROVED)
        self.assertEqual(event.remote_uuid, remote_uuid)
        self.assertEqual(event.remote_event_id, "135260000000002")
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "aprovado")

    def test_multiple_corrections_preserve_sequence_protocol_and_history_order(self) -> None:
        first_event = self._emit_success(event_sequence=1, protocol="135260000000101")
        second_event = self._emit_success(event_sequence=2, protocol="135260000000102")

        detail_request = RequestFactory().get("/")
        detail_request.user = self.user
        detail_request.session = {}
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            detail_response = NfeRequestDetailView.as_view()(detail_request, pk=self.item.request_id)
            detail_response.render()

        self.assertEqual(list(detail_response.context_data["cce_events"]), [first_event, second_event])
        self.assertContains(detail_response, "135260000000101")
        self.assertContains(detail_response, "135260000000102")
        self.assertContains(detail_response, CORRECTION_TEXT, count=2)
        self.assertContains(detail_response, "Evento de carta de correcao registrado", count=2)
        self.assertContains(detail_response, "<td>Aprovado</td>", count=2, html=True)

    def test_ambiguous_webhook_does_not_update_events_across_workshops(self) -> None:
        from apps.core.infrastructure.services.webmania.webmania_webhooks import process_webhook_event, store_webhook_event

        shared_access_key = "35123456789012345678901234567890123456789099"
        first_item = self._create_nfe_item(workshop=self.workshop, suffix=20, access_key=shared_access_key)
        second_item = self._create_nfe_item(workshop=self.other_workshop, suffix=21, access_key=shared_access_key)
        first_event = self._emit_timeout(item=first_item)
        second_event = self._emit_timeout(item=second_item)
        remote_uuid = str(uuid4())
        webhook = store_webhook_event(payload={"modelo": "cce", "uuid": remote_uuid, "status": "aprovado", "chave": shared_access_key, "evento": 1})

        self.assertFalse(process_webhook_event(webhook))
        webhook.refresh_from_db()
        first_event.refresh_from_db()
        second_event.refresh_from_db()
        self.assertIn("ambigua", webhook.processing_error)
        self.assertEqual(first_event.status, FiscalDocumentEventStatus.UNCERTAIN)
        self.assertEqual(second_event.status, FiscalDocumentEventStatus.UNCERTAIN)
        self.assertFalse(FiscalDocumentEvent.objects.filter(remote_uuid=remote_uuid).exists())

    def test_reconciliation_is_get_only_and_validates_remote_identity(self) -> None:
        event = self._emit_timeout()
        event.remote_uuid = str(uuid4())
        event.save(update_fields=["remote_uuid"])
        response_payload = {
            "uuid": event.remote_uuid,
            "modelo": "cce",
            "status": "aprovado",
            "evento": event.event_sequence,
            "chave": self.item.access_key,
            "xml": "https://example.test/reconciled-cce.xml",
        }

        with (
            patch("apps.finance.services.nfe_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_events.requests.get", return_value=_mock_response(response_payload)) as get_mock,
            patch("apps.finance.services.nfe_events.requests.post") as post_mock,
        ):
            reconciled = reconcile_cce_event(event=event)

        get_mock.assert_called_once()
        post_mock.assert_not_called()
        self.assertEqual(reconciled.status, FiscalDocumentEventStatus.APPROVED)
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document_event=event)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)

        mismatched_payload = dict(response_payload, uuid=str(uuid4()))
        event.status = FiscalDocumentEventStatus.UNCERTAIN
        event.save(update_fields=["status"])
        with (
            patch("apps.finance.services.nfe_events._build_headers", return_value={}),
            patch("apps.finance.services.nfe_events.requests.get", return_value=_mock_response(mismatched_payload)),
        ):
            with self.assertRaisesMessage(NfeCorrectionError, "documento diferente"):
                reconcile_cce_event(event=event)
        event.refresh_from_db()
        self.assertEqual(event.status, FiscalDocumentEventStatus.UNCERTAIN)

    def test_reconciliation_rejects_invalid_local_uuid_without_remote_request(self) -> None:
        event = self._emit_timeout()
        event.remote_uuid = "uuid-invalido"
        event.save(update_fields=["remote_uuid"])

        with patch("apps.finance.services.nfe_events.requests.get") as get_mock:
            with self.assertRaisesMessage(NfeCorrectionError, "UUID remoto inválido"):
                reconcile_cce_event(event=event)

        get_mock.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.status, FiscalDocumentEventStatus.UNCERTAIN)

    def test_webhook_with_mismatched_nfe_identity_is_deferred_without_state_change(self) -> None:
        from apps.core.infrastructure.services.webmania.webmania_webhooks import process_webhook_event, store_webhook_event

        event = self._emit_timeout()
        remote_uuid = str(uuid4())
        event.remote_uuid = remote_uuid
        event.save(update_fields=["remote_uuid"])
        webhook = store_webhook_event(
            payload={
                "modelo": "cce",
                "uuid": remote_uuid,
                "status": "aprovado",
                "chave": "35" + ("9" * 42),
                "evento": event.event_sequence,
            }
        )

        self.assertFalse(process_webhook_event(webhook))
        webhook.refresh_from_db()
        event.refresh_from_db()
        self.assertIn("outra NF-e", webhook.processing_error)
        self.assertEqual(event.status, FiscalDocumentEventStatus.UNCERTAIN)
        self.assertFalse(webhook.processed_at)

    def test_webhook_does_not_regress_approved_cce_to_processing(self) -> None:
        from apps.core.infrastructure.services.webmania.webmania_webhooks import process_webhook_event, store_webhook_event

        event = self._emit_success()
        webhook = store_webhook_event(
            payload={
                "modelo": "cce",
                "uuid": event.remote_uuid,
                "status": "processando",
                "chave": self.item.access_key,
                "evento": event.event_sequence,
            }
        )

        self.assertTrue(process_webhook_event(webhook))
        event.refresh_from_db()
        self.assertEqual(event.status, FiscalDocumentEventStatus.APPROVED)

    def test_nfse_webhook_handler_remains_unchanged(self) -> None:
        from apps.core.infrastructure.services.webmania.webmania_webhooks import process_webhook_event, store_webhook_event

        nfse_request = NfseRequest.objects.create(workshop=self.workshop, workorder=self.item.workorder)
        nfse_item = NfseItem.objects.create(
            workshop=self.workshop,
            workorder=self.item.workorder,
            request=nfse_request,
            batch=None,
            uuid=uuid4(),
        )
        payload = {"modelo": "nfse", "uuid": str(nfse_item.uuid), "status": "aprovado"}
        webhook = store_webhook_event(payload=payload)

        with patch("apps.core.infrastructure.services.webmania.webmania_webhooks.apply_nfse_item_payload", return_value=nfse_item) as apply_mock:
            self.assertTrue(process_webhook_event(webhook))

        apply_mock.assert_called_once()
        self.assertEqual(apply_mock.call_args.kwargs["item"], nfse_item)
        self.assertEqual(apply_mock.call_args.kwargs["response_payload"], payload)
        webhook.refresh_from_db()
        self.assertIsNotNone(webhook.processed_at)

    def test_management_reconciliation_uses_existing_cce_uuid_without_post(self) -> None:
        event = self._emit_timeout()
        event.remote_uuid = str(uuid4())
        event.save(update_fields=["remote_uuid"])

        with (
            patch("apps.finance.management.commands.reconcile_webmania_documents.process_pending_webhook_events", return_value=0),
            patch("apps.finance.management.commands.reconcile_webmania_documents.get_fiscal_service"),
            patch("apps.finance.management.commands.reconcile_webmania_documents.reconcile_cce_event", return_value=event) as reconcile_mock,
            patch("apps.finance.services.nfe_events.requests.post") as post_mock,
        ):
            call_command("reconcile_webmania_documents", limit=10, stdout=StringIO())

        reconcile_mock.assert_called_once()
        self.assertEqual(reconcile_mock.call_args.kwargs["event"].pk, event.pk)
        post_mock.assert_not_called()

    def test_issue_requires_specific_permission_and_active_workshop_scope(self) -> None:
        request = RequestFactory().post("/", data={"correction": CORRECTION_TEXT, "confirm_legal_restrictions": "on"})
        request.user = self.user

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
        ):
            with self.assertRaises(PermissionDenied):
                NfeCorrectionIssueView.as_view()(request, pk=self.item.request_id)

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfeCorrectionIssueView.as_view()(request, pk=self.item.request_id)

    def test_history_and_downloads_reuse_existing_detail_and_protected_gateway(self) -> None:
        event = self._emit_success()
        detail_request = RequestFactory().get("/")
        detail_request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            detail_response = NfeRequestDetailView.as_view()(detail_request, pk=self.item.request_id)

        self.assertEqual(list(detail_response.context_data["cce_events"]), [event])

        downloaded = SimpleNamespace(content=b"documento-cce", content_type="application/octet-stream")
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfe.download_webmania_document", return_value=downloaded) as download_mock,
        ):
            for document_kind, expected_url in (("xml", event.xml_url), ("dacce", event.dacce_url)):
                download_request = RequestFactory().get("/")
                download_request.user = self.user
                download_response = NfeCorrectionDownloadView.as_view()(download_request, pk=self.item.request_id, event_pk=event.pk, document=document_kind)

                self.assertEqual(download_response.status_code, 200)
                download_mock.assert_called_with(workshop=self.workshop, url=expected_url)

        cross_workshop_request = RequestFactory().get("/")
        cross_workshop_request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                NfeCorrectionDownloadView.as_view()(cross_workshop_request, pk=self.item.request_id, event_pk=event.pk, document="xml")

        self.assertEqual(WebmaniaWebhookEvent.objects.count(), 0)
