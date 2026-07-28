from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import requests
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.models import Account, User
from apps.budget.models import Budget
from apps.finance.models.finance import (
    FiscalDocument,
    FiscalDocumentLink,
    FiscalDocumentLinkRole,
    FiscalDocumentOrigin,
    FiscalDocumentPurpose,
    FiscalDocumentStatus,
    FiscalEmissionAttempt,
    FiscalEmissionAttemptStatus,
    NfeItem,
    NfeRequest,
)
from apps.finance.services.nfe_returns import (
    NfeReturnError,
    calculate_available_return_quantities,
    create_nfe_return_draft_from_item,
    reconcile_nfe_return_document,
    transmit_nfe_return_document,
)
from apps.finance.views.nfe import NfeReturnDownloadView
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def _mock_response(payload: dict[str, object]) -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


class NfeReturnOperationalTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Devolucao")
        self.workshop = self._create_workshop(suffix=10)
        self.other_workshop = self._create_workshop(suffix=11)
        self.user = User.objects.create_user(username="fiscal-devolucao", password="test", cpf="98765432100")
        self.user.account = self.account
        self.user.save(update_fields=["account"])

    def _create_workshop(self, *, suffix: int) -> Workshop:
        return Workshop.objects.create(
            account=self.account,
            name=f"Oficina Devolucao {suffix}",
            cnpj=f"12.345.678/0001-{suffix:02d}",
            phone=f"+5511999999{suffix:03d}",
            address=f"Rua Devolucao, {suffix}",
        )

    def _create_nfe_item(
        self,
        *,
        workshop: Workshop | None = None,
        suffix: int = 20,
        products: list[dict[str, object]] | None = None,
    ) -> NfeItem:
        selected_workshop = workshop or self.workshop
        budget = Budget.objects.create(workshop=selected_workshop, entry_date=timezone.localdate())
        workorder = WorkOrder.objects.create(workshop=selected_workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=selected_workshop, workorder=workorder, tax_class="REFNFE")
        return NfeItem.objects.create(
            workshop=selected_workshop,
            workorder=workorder,
            request=nfe_request,
            uuid=uuid4(),
            status="aprovado",
            access_key=f"35{suffix:042d}"[-44:],
            number=str(1000 + suffix),
            series="1",
            xml_url=f"https://example.test/nfe-original-{suffix}.xml",
            raw_payload={
                "produtos": products
                or [
                    {"sequencial": 1, "codigo": "P1", "quantidade": "2"},
                    {"sequencial": 2, "codigo": "P2", "quantidade": "3"},
                ]
            },
        )

    def _draft(
        self,
        *,
        item: NfeItem,
        products: list[dict[str, object]],
        purpose: str = FiscalDocumentPurpose.RETURN,
    ) -> FiscalDocument:
        return create_nfe_return_draft_from_item(
            item=item,
            purpose=purpose,
            products=products,
            requested_by=self.user,
            natureza_operacao="Devolucao de mercadoria",
            codigo_cfop="1202",
        )

    def _remote_payload(
        self,
        *,
        status: str = "aprovado",
        remote_uuid: str | None = None,
        access_key: str | None = None,
    ) -> dict[str, object]:
        return {
            "uuid": remote_uuid or str(uuid4()),
            "modelo": "nfe",
            "status": status,
            "nfe": "9001",
            "serie": "1",
            "recibo": "REC-RETURN",
            "chave": access_key or f"35{9001:042d}"[-44:],
            "xml": "https://example.test/devolucao.xml",
            "danfe": "https://example.test/devolucao.pdf",
            "log": {"authorization": "secret"},
        }

    def _transmit(self, *, document: FiscalDocument, payload: dict[str, object] | None = None) -> FiscalDocument:
        with (
            patch("apps.finance.services.nfe_returns._build_headers", return_value={}),
            patch("apps.finance.services.nfe_returns.requests.post", return_value=_mock_response(payload or self._remote_payload())),
        ):
            return transmit_nfe_return_document(document=document)

    def test_total_return_creates_separate_linked_document_and_reserves_full_balance(self) -> None:
        item = self._create_nfe_item()
        original_xml = item.xml_url
        original_snapshot = item.raw_payload

        document = self._transmit(document=self._draft(item=item, products=[]))

        original = FiscalDocument.objects.get(legacy_nfe_item=item)
        link = FiscalDocumentLink.objects.get(document=document)
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document=document)
        self.assertEqual(document.origin, FiscalDocumentOrigin.DERIVED)
        self.assertEqual(document.purpose, FiscalDocumentPurpose.RETURN)
        self.assertEqual(document.requested_by, self.user)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(link.related_document, original)
        self.assertEqual(link.role, FiscalDocumentLinkRole.RETURNS)
        self.assertNotIn("produtos", document.request_payload)
        self.assertNotIn("quantidade", document.request_payload)
        self.assertEqual(calculate_available_return_quantities(original_document=original), {1: 0, 2: 0})
        item.refresh_from_db()
        self.assertEqual(item.xml_url, original_xml)
        self.assertEqual(item.raw_payload, original_snapshot)
        self.assertEqual(original.status, FiscalDocumentStatus.APPROVED)

    def test_partial_return_preserves_multiple_original_item_sequences_and_balances(self) -> None:
        item = self._create_nfe_item()
        document = self._transmit(
            document=self._draft(
                item=item,
                products=[
                    {"sequencial": 2, "quantidade": "1.5"},
                    {"sequencial": 1, "quantidade": "1"},
                ],
            )
        )

        original = FiscalDocumentLink.objects.get(document=document).related_document
        self.assertEqual(document.request_payload["produtos"], [2, 1])
        self.assertEqual(document.request_payload["quantidade"], ["1.5", "1"])
        self.assertEqual(calculate_available_return_quantities(original_document=original), {1: 1, 2: 1.5})

        original.request_payload = item.raw_payload
        original.response_payload = item.raw_payload
        original.save(update_fields=["request_payload", "response_payload"])
        self.assertEqual(calculate_available_return_quantities(original_document=original), {1: 1, 2: 1.5})

    def test_partial_return_rejects_insufficient_balance_unknown_and_duplicate_items(self) -> None:
        item = self._create_nfe_item(products=[{"sequencial": 1, "codigo": "P1", "quantidade": "2"}])
        first = self._transmit(document=self._draft(item=item, products=[{"sequencial": 1, "quantidade": "1.5"}]))

        with self.assertRaisesMessage(NfeReturnError, "excede o saldo"):
            self._draft(item=item, products=[{"sequencial": 1, "quantidade": "1"}])
        with self.assertRaisesMessage(NfeReturnError, "nao foi encontrado"):
            self._draft(item=item, products=[{"sequencial": 99, "quantidade": "1"}])
        with self.assertRaisesMessage(NfeReturnError, "mais de uma vez"):
            self._draft(
                item=item,
                products=[
                    {"sequencial": 1, "quantidade": "0.25"},
                    {"sequencial": 1, "quantidade": "0.25"},
                ],
            )

        original = FiscalDocumentLink.objects.get(document=first).related_document
        self.assertEqual(calculate_available_return_quantities(original_document=original), {1: 0.5})
        self.assertEqual(FiscalDocument.objects.filter(origin=FiscalDocumentOrigin.DERIVED).count(), 1)

    def test_partial_return_without_original_item_snapshot_is_blocked_before_post(self) -> None:
        item = self._create_nfe_item(products=[])
        item.raw_payload = {}
        item.save(update_fields=["raw_payload"])

        with patch("apps.finance.services.nfe_returns.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeReturnError, "nao possui snapshot de itens"):
                self._draft(item=item, products=[{"sequencial": 1, "quantidade": "1"}])

        post_mock.assert_not_called()
        self.assertFalse(FiscalDocument.objects.filter(origin=FiscalDocumentOrigin.DERIVED).exists())

    def test_total_return_after_partial_is_blocked_by_available_balance(self) -> None:
        item = self._create_nfe_item(products=[{"sequencial": 1, "codigo": "P1", "quantidade": "2"}])
        self._transmit(document=self._draft(item=item, products=[{"sequencial": 1, "quantidade": "1"}]))

        with patch("apps.finance.services.nfe_returns.requests.post") as post_mock:
            with self.assertRaisesMessage(NfeReturnError, "saldo disponivel"):
                self._draft(item=item, products=[])

        post_mock.assert_not_called()

    def test_same_derived_intention_cannot_be_transmitted_twice(self) -> None:
        item = self._create_nfe_item()
        document = self._draft(item=item, products=[{"sequencial": 1, "quantidade": "1"}])
        with (
            patch("apps.finance.services.nfe_returns._build_headers", return_value={}),
            patch("apps.finance.services.nfe_returns.requests.post", return_value=_mock_response(self._remote_payload())) as post_mock,
        ):
            transmit_nfe_return_document(document=document)
            with self.assertRaisesMessage(NfeReturnError, "ja possui envio remoto"):
                transmit_nfe_return_document(document=document)

        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(FiscalEmissionAttempt.objects.filter(fiscal_document=document).count(), 1)

    def test_timeout_stays_uncertain_reserves_balance_and_never_resends(self) -> None:
        item = self._create_nfe_item(products=[{"sequencial": 1, "codigo": "P1", "quantidade": "1"}])
        document = self._draft(item=item, products=[{"sequencial": 1, "quantidade": "1"}])
        with (
            patch("apps.finance.services.nfe_returns._build_headers", return_value={}),
            patch("apps.finance.services.nfe_returns.requests.post", side_effect=requests.Timeout("timeout")) as post_mock,
        ):
            with self.assertRaisesMessage(NfeReturnError, "estado remoto incerto"):
                transmit_nfe_return_document(document=document)
            with self.assertRaisesMessage(NfeReturnError, "estado remoto incerto"):
                transmit_nfe_return_document(document=document)
            with self.assertRaisesMessage(NfeReturnError, "excede o saldo"):
                self._draft(item=item, products=[{"sequencial": 1, "quantidade": "1"}])

        document.refresh_from_db()
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document=document)
        self.assertEqual(post_mock.call_count, 1)
        self.assertEqual(document.status, FiscalDocumentStatus.UNCERTAIN)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.UNCERTAIN)

    def test_inconclusive_response_stays_uncertain_and_preserves_remote_payload(self) -> None:
        item = self._create_nfe_item()
        document = self._draft(item=item, products=[{"sequencial": 1, "quantidade": "1"}])
        response_payload = {"modelo": "nfe", "status": "processando", "log": {"authorization": "secret"}}

        with (
            patch("apps.finance.services.nfe_returns._build_headers", return_value={}),
            patch("apps.finance.services.nfe_returns.requests.post", return_value=_mock_response(response_payload)),
        ):
            with self.assertRaisesMessage(NfeReturnError, "Resposta inconclusiva"):
                transmit_nfe_return_document(document=document)

        document.refresh_from_db()
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document=document)
        self.assertEqual(document.status, FiscalDocumentStatus.UNCERTAIN)
        self.assertEqual(document.response_payload["status"], "processando")
        self.assertEqual(document.response_payload["log"]["authorization"], "[REDACTED]")
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.UNCERTAIN)

    def test_webhook_completes_processing_document_and_linked_attempt(self) -> None:
        from apps.core.infrastructure.services.webmania.webmania_webhooks import process_pending_webhook_events, store_webhook_event

        item = self._create_nfe_item()
        remote_uuid = str(uuid4())
        document = self._transmit(
            document=self._draft(item=item, products=[{"sequencial": 1, "quantidade": "1"}]),
            payload={"uuid": remote_uuid, "modelo": "nfe", "status": "processando"},
        )
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document=document)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SENT)

        webhook_payload = self._remote_payload(remote_uuid=remote_uuid)
        store_webhook_event(payload=webhook_payload)
        self.assertEqual(process_pending_webhook_events(model="nfe", event_uuid=remote_uuid), 1)

        document.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(document.status, FiscalDocumentStatus.APPROVED)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)
        self.assertEqual(document.xml_url, "https://example.test/devolucao.xml")

    def test_ambiguous_webhook_does_not_update_return_across_workshops(self) -> None:
        from apps.core.infrastructure.services.webmania.webmania_webhooks import process_webhook_event, store_webhook_event

        shared_key = "35123456789012345678901234567890123456789099"
        first = FiscalDocument.objects.create(
            workshop=self.workshop,
            account=self.account,
            document_type="nfe",
            origin=FiscalDocumentOrigin.DERIVED,
            purpose=FiscalDocumentPurpose.RETURN,
            status=FiscalDocumentStatus.PROCESSING,
            access_key=shared_key,
        )
        second = FiscalDocument.objects.create(
            workshop=self.other_workshop,
            account=self.account,
            document_type="nfe",
            origin=FiscalDocumentOrigin.DERIVED,
            purpose=FiscalDocumentPurpose.RETURN,
            status=FiscalDocumentStatus.PROCESSING,
            access_key=shared_key,
        )
        webhook = store_webhook_event(payload={"modelo": "nfe", "status": "aprovado", "chave": shared_key})

        self.assertFalse(process_webhook_event(webhook))
        webhook.refresh_from_db()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIn("ambigu", webhook.processing_error)
        self.assertEqual(first.status, FiscalDocumentStatus.PROCESSING)
        self.assertEqual(second.status, FiscalDocumentStatus.PROCESSING)

    def test_reconciliation_is_get_only_validates_identity_and_completes_attempt(self) -> None:
        item = self._create_nfe_item()
        remote_uuid = str(uuid4())
        document = self._transmit(
            document=self._draft(item=item, products=[{"sequencial": 1, "quantidade": "1"}]),
            payload={"uuid": remote_uuid, "modelo": "nfe", "status": "processando"},
        )

        mismatched = self._remote_payload(remote_uuid=str(uuid4()))
        with (
            patch("apps.finance.services.nfe_returns._build_headers", return_value={}),
            patch("apps.finance.services.nfe_returns.requests.get", return_value=_mock_response(mismatched)),
            patch("apps.finance.services.nfe_returns.requests.post") as post_mock,
        ):
            with self.assertRaisesMessage(NfeReturnError, "NF-e diferente"):
                reconcile_nfe_return_document(document=document)
        post_mock.assert_not_called()
        document.refresh_from_db()
        self.assertEqual(document.status, FiscalDocumentStatus.PROCESSING)

        response_payload = self._remote_payload(remote_uuid=remote_uuid)
        with (
            patch("apps.finance.services.nfe_returns._build_headers", return_value={}),
            patch("apps.finance.services.nfe_returns.requests.get", return_value=_mock_response(response_payload)) as get_mock,
            patch("apps.finance.services.nfe_returns.requests.post") as post_mock,
        ):
            reconciled = reconcile_nfe_return_document(document=document)

        get_mock.assert_called_once()
        post_mock.assert_not_called()
        attempt = FiscalEmissionAttempt.objects.get(fiscal_document=document)
        self.assertEqual(reconciled.status, FiscalDocumentStatus.APPROVED)
        self.assertEqual(attempt.status, FiscalEmissionAttemptStatus.SUCCEEDED)

    def test_existing_download_gateway_remains_scoped_to_original_nfe(self) -> None:
        item = self._create_nfe_item()
        document = self._transmit(document=self._draft(item=item, products=[]))
        request = RequestFactory().get("/")
        request.user = self.user
        downloaded = SimpleNamespace(content=b"xml-return", content_type="application/xml")

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
            patch("apps.finance.views.nfe.download_webmania_document", return_value=downloaded) as download_mock,
        ):
            response = NfeReturnDownloadView.as_view()(request, pk=item.request_id, document_pk=document.pk, document="xml")

        self.assertEqual(response.status_code, 200)
        download_mock.assert_called_once_with(workshop=self.workshop, url=document.xml_url)
