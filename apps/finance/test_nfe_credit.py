from __future__ import annotations

import threading
import time
from decimal import Decimal
from typing import Any
from unittest.mock import Mock, patch

import requests
from django.db import close_old_connections
from django.test import RequestFactory, TestCase, TransactionTestCase

from apps.accounts.models import Account, User
from apps.budget.models import Budget, BudgetStatus
from apps.customer.models import Customer
from apps.finance.models.finance import (
    FiscalCreditProductPreview,
    FiscalDocument,
    FiscalDocumentLink,
    FiscalDocumentLinkRole,
    FiscalDocumentPurpose,
    FiscalDocumentStatus,
    FiscalEmissionAttempt,
    FiscalEmissionAttemptStatus,
    FiscalEmissionOperationType,
    FiscalProductPreviewStatus,
    FiscalReferencedBasis,
    FiscalReferencedBasisItem,
    FiscalReferencedBasisStatus,
    NfeItem,
    NfeRequest,
    WebmaniaCompany,
    WebmaniaWebhookEvent,
)
from apps.finance.services.nfe_credit import NfeCreditError, create_and_emit_nfe_credit_type_one, reconcile_nfe_credit_document
from apps.core.infrastructure.services.webmania.webmania_webhooks import process_webhook_event
from apps.finance.views.nfe_credit import NfeCreditIssueView, NfeCreditPayloadView
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def _response(payload: dict[str, Any]) -> Mock:
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


class CreditFixtureMixin:
    def build_fixture(self, *, suffix: int = 71) -> FiscalCreditProductPreview:
        self.user = User.objects.create_user(username=f"credit{suffix}", password="test", cpf=f"76543210{suffix:03d}")
        account = Account.objects.create(name=f"Conta Credito {suffix}", owner=self.user)
        self.user.account = account
        self.user.is_account_owner = True
        self.user.save(update_fields=["account", "is_account_owner"])
        self.workshop = Workshop.objects.create(account=account, name=f"Oficina Credito {suffix}", cnpj=f"33.345.678/0001-{suffix:02d}", phone="+5511999999999", address="Rua Credito, 1")
        WebmaniaCompany.objects.create(workshop=self.workshop, credit_debit_basis_enabled=True)
        customer = Customer.objects.create(workshop=self.workshop, customer_type="PF", name="Cliente Credito", cpf_or_cnpj="12345678901", email="credito@example.test", logradouro="Rua Teste", numero="123", bairro="Centro", cidade="Sao Paulo", estado="SP", cep="01001-000")
        budget = Budget.objects.create(workshop=self.workshop, entry_date="2026-06-22", status=BudgetStatus.APPROVED, customer=customer)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder)
        nfe_item = NfeItem.objects.create(workshop=self.workshop, workorder=workorder, request=nfe_request, uuid=f"12345678-1234-4234-8234-123456789{suffix:03d}"[-36:], status="aprovado", access_key=f"35{suffix:042d}"[-44:], raw_payload={"produtos": [{"item": 1}]})
        source = FiscalDocument.objects.create(workshop=self.workshop, account=account, legacy_nfe_item=nfe_item, remote_uuid=str(nfe_item.uuid), access_key=nfe_item.access_key, status=FiscalDocumentStatus.APPROVED)
        basis = FiscalReferencedBasis.objects.create(workshop=self.workshop, source_document=source, source_nfe_item=nfe_item, source_access_key=nfe_item.access_key, source_item_sequence=1, basis_type="credit", fiscal_hypothesis="credit_fine_interest", ibs_cbs_snapshot={"situacao_tributaria": "000", "classificacao_tributaria": "000001"}, status=FiscalReferencedBasisStatus.APPROVED, approved_by=self.user)
        item = FiscalReferencedBasisItem.objects.create(basis=basis, source_item_sequence=1, source_item_description="Multa e juros", source_item_code="MJ-1", source_item_ncm="00000000", source_item_cfop="5949", source_quantity=Decimal("1"), source_unit="UN", source_unit_price=Decimal("7"), source_total_amount=Decimal("7"), fine_amount=Decimal("5"), interest_amount=Decimal("2"), credit_debit_base_amount=Decimal("7"), commercial_snapshot={"source": "xml"}, monetary_snapshot={"fine": "5", "interest": "2"})
        return FiscalCreditProductPreview.objects.create(workshop=self.workshop, basis=basis, basis_item=item, revision=1, source_access_key=nfe_item.access_key, source_item_sequence=1, product_cfop="5949", product_quantity=Decimal("1"), product_unit_price=Decimal("7"), product_total_amount=Decimal("7"), product_payload={"nome": "Multa e juros", "codigo": "MJ-1", "ncm": "00000000", "quantidade": "1.000000", "unidade": "UN", "subtotal": "7.00", "total": "7.00", "codigo_cfop": "5949", "impostos": {"ibs_cbs": basis.ibs_cbs_snapshot}}, ibs_cbs_payload=basis.ibs_cbs_snapshot, preview_payload={"modelo": 1, "finalidade": 5, "tipo_credito": 1, "nfe_referenciada": [nfe_item.access_key]}, validation_status=FiscalProductPreviewStatus.APPROVED, explicit_value_confirmation=True, created_by=self.user, approved_by=self.user)

    @staticmethod
    def success_payload() -> dict[str, Any]:
        return {"uuid": "22345678-1234-4234-8234-123456789071", "modelo": "nfe", "status": "aprovado", "nfe": "7001", "serie": "1", "recibo": "REC-CREDIT", "chave": "35123456789012345678901234567890123456789071", "xml": "https://example.test/credit.xml", "danfe": "https://example.test/credit.pdf", "log": {"token": "secret"}}


class FiscalPhaseTwoCreditTypeOneTests(CreditFixtureMixin, TestCase):
    def setUp(self) -> None:
        self.preview = self.build_fixture()

    def emit(self, **kwargs: Any) -> FiscalDocument:
        data = {"preview": self.preview, "workshop": self.workshop, "requested_by": self.user, "legal_confirmation": True}
        data.update(kwargs)
        with patch("apps.finance.services.nfe_credit._build_headers", return_value={}), patch("apps.finance.services.nfe_credit.requests.post", return_value=_response(self.success_payload())) as post:
            document = create_and_emit_nfe_credit_type_one(**data)
        self.post_mock = post
        return document

    def test_contract_uses_preview_and_only_ibs_cbs(self) -> None:
        document = self.emit()
        payload = self.post_mock.call_args.kwargs["json"]
        self.assertEqual((payload["modelo"], payload["finalidade"], payload["tipo_credito"]), (1, 5, 1))
        self.assertEqual(payload["nfe_referenciada"], [self.preview.source_access_key])
        self.assertEqual(payload["produtos"], [self.preview.product_payload])
        self.assertEqual(set(payload["produtos"][0]["impostos"]), {"ibs_cbs"})
        self.assertEqual(payload["produtos"][0]["codigo_cfop"], "5949")
        self.assertIn("cliente", payload)
        self.assertIn("pedido", payload)
        forbidden = {"tipo_debito", "dfe_referenciado", "cod_evento", "evento_ibs_cbs", "imposto_devolvido"}
        self.assertFalse(forbidden.intersection(payload))
        self.assertFalse({"icms", "ipi", "pis", "cofins", "issqn", "ii"}.intersection(payload["produtos"][0]["impostos"]))
        self.assertEqual(document.purpose, FiscalDocumentPurpose.CREDIT)

    def test_model_links_preview_basis_and_original_without_mutating_sources(self) -> None:
        source_status = self.preview.basis.source_document.status
        preview_payload = dict(self.preview.product_payload)
        document = self.emit()
        self.assertEqual(document.fiscal_purpose_type, "1")
        self.assertEqual(document.referenced_basis, self.preview.basis)
        self.assertEqual(document.credit_product_preview, self.preview)
        link = FiscalDocumentLink.objects.get(document=document)
        self.assertEqual(link.role, FiscalDocumentLinkRole.CREDITS)
        self.preview.refresh_from_db()
        self.preview.basis.source_document.refresh_from_db()
        self.assertEqual(self.preview.product_payload, preview_payload)
        self.assertEqual(self.preview.basis.source_document.status, source_status)

    def test_document_and_attempt_exist_before_gateway_and_payload_is_frozen(self) -> None:
        def inspect_before_response(*args: Any, **kwargs: Any) -> Mock:
            document = FiscalDocument.objects.get(credit_product_preview=self.preview)
            attempt = FiscalEmissionAttempt.objects.get(fiscal_document=document)
            self.assertEqual(attempt.operation_type, FiscalEmissionOperationType.NFE_CREDIT_EMISSION)
            self.assertEqual(attempt.request_payload, kwargs["json"])
            return _response(self.success_payload())

        with patch("apps.finance.services.nfe_credit._build_headers", return_value={}), patch("apps.finance.services.nfe_credit.requests.post", side_effect=inspect_before_response):
            document = create_and_emit_nfe_credit_type_one(preview=self.preview, workshop=self.workshop, requested_by=self.user, legal_confirmation=True)
        self.assertEqual(document.emission_attempts.get().request_payload, document.request_payload)

    def test_retry_same_preview_is_blocked_without_remote_call(self) -> None:
        self.emit()
        with patch("apps.finance.services.nfe_credit.requests.post") as post, self.assertRaisesMessage(NfeCreditError, "ja possui"):
            create_and_emit_nfe_credit_type_one(preview=self.preview, workshop=self.workshop, requested_by=self.user, legal_confirmation=True)
        post.assert_not_called()

    def test_timeout_marks_uncertain_and_blocks_retry(self) -> None:
        with patch("apps.finance.services.nfe_credit._build_headers", return_value={}), patch("apps.finance.services.nfe_credit.requests.post", side_effect=requests.Timeout), self.assertRaisesMessage(NfeCreditError, "incerto"):
            create_and_emit_nfe_credit_type_one(preview=self.preview, workshop=self.workshop, requested_by=self.user, legal_confirmation=True)
        document = FiscalDocument.objects.get(credit_product_preview=self.preview)
        self.assertEqual(document.status, FiscalDocumentStatus.UNCERTAIN)
        self.assertEqual(document.emission_attempts.get().status, FiscalEmissionAttemptStatus.UNCERTAIN)
        with patch("apps.finance.services.nfe_credit.requests.post") as post, self.assertRaises(NfeCreditError):
            create_and_emit_nfe_credit_type_one(preview=self.preview, workshop=self.workshop, requested_by=self.user, legal_confirmation=True)
        post.assert_not_called()

    def test_eligibility_blocks_draft_flag_cross_workshop_and_invalid_payload(self) -> None:
        FiscalCreditProductPreview.objects.filter(pk=self.preview.pk).update(validation_status=FiscalProductPreviewStatus.DRAFT)
        self.preview.refresh_from_db()
        with self.assertRaisesMessage(NfeCreditError, "aprovada"):
            self.emit()
        FiscalCreditProductPreview.objects.filter(pk=self.preview.pk).update(validation_status=FiscalProductPreviewStatus.APPROVED)
        WebmaniaCompany.objects.filter(workshop=self.workshop).update(credit_debit_basis_enabled=False)
        self.preview.refresh_from_db()
        with self.assertRaisesMessage(NfeCreditError, "desabilitada"):
            self.emit()

    def test_forbidden_tax_or_zero_total_is_blocked(self) -> None:
        self.preview.product_payload["impostos"]["icms"] = {"cst": "00"}
        FiscalCreditProductPreview.objects.filter(pk=self.preview.pk).update(product_payload=self.preview.product_payload)
        self.preview.refresh_from_db()
        with self.assertRaisesMessage(NfeCreditError, "proibidos"):
            self.emit()
        FiscalCreditProductPreview.objects.filter(pk=self.preview.pk).update(product_payload={**self.preview.product_payload, "impostos": {"ibs_cbs": self.preview.ibs_cbs_payload}})
        FiscalReferencedBasisItem.objects.filter(pk=self.preview.basis_item_id).update(credit_debit_base_amount=Decimal("0"))
        self.preview.refresh_from_db()
        with self.assertRaisesMessage(NfeCreditError, "positivo"):
            self.emit()

    def test_webhook_updates_only_credit_document_and_is_idempotent(self) -> None:
        document = self.emit()
        source = self.preview.basis.source_document
        payload = {**self.success_payload(), "status": "aprovado", "xml": "https://example.test/final-credit.xml"}
        event = WebmaniaWebhookEvent.objects.create(model="nfe", event_uuid=payload["uuid"], fingerprint="credit-webhook-1", payload=payload)
        self.assertTrue(process_webhook_event(event))
        self.assertTrue(process_webhook_event(event))
        document.refresh_from_db()
        source.refresh_from_db()
        self.assertEqual(document.xml_url, payload["xml"])
        self.assertEqual(source.status, FiscalDocumentStatus.APPROVED)

    def test_ambiguous_webhook_does_not_update_any_credit_document(self) -> None:
        first_document = self.emit()
        first_workshop = self.workshop
        second_preview = self.build_fixture(suffix=73)
        with patch("apps.finance.services.nfe_credit._build_headers", return_value={}), patch("apps.finance.services.nfe_credit.requests.post", return_value=_response(self.success_payload())):
            second_document = create_and_emit_nfe_credit_type_one(preview=second_preview, workshop=self.workshop, requested_by=self.user, legal_confirmation=True)
        payload = {**self.success_payload(), "status": "cancelado"}
        event = WebmaniaWebhookEvent.objects.create(model="nfe", event_uuid=payload["uuid"], fingerprint="credit-webhook-ambiguous", payload=payload)
        self.assertFalse(process_webhook_event(event))
        first_document.refresh_from_db()
        second_document.refresh_from_db()
        self.assertEqual(first_document.status, FiscalDocumentStatus.APPROVED)
        self.assertEqual(second_document.status, FiscalDocumentStatus.APPROVED)
        self.assertNotEqual(first_workshop.pk, self.workshop.pk)

    def test_reconciliation_queries_without_reemitting(self) -> None:
        with patch("apps.finance.services.nfe_credit._build_headers", return_value={}), patch("apps.finance.services.nfe_credit.requests.post", side_effect=requests.Timeout), self.assertRaises(NfeCreditError):
            create_and_emit_nfe_credit_type_one(preview=self.preview, workshop=self.workshop, requested_by=self.user, legal_confirmation=True)
        document = FiscalDocument.objects.get(credit_product_preview=self.preview)
        FiscalEmissionAttempt.objects.filter(fiscal_document=document).update(remote_uuid="22345678-1234-4234-8234-123456789071")
        with patch("apps.finance.services.nfe_credit._build_headers", return_value={}), patch("apps.finance.services.nfe_credit.requests.get", return_value=_response(self.success_payload())) as get, patch("apps.finance.services.nfe_credit.requests.post") as post:
            reconciled = reconcile_nfe_credit_document(document=document)
        self.assertEqual(reconciled.status, FiscalDocumentStatus.APPROVED)
        get.assert_called_once()
        post.assert_not_called()

    def test_issue_permission_is_specific_and_payload_is_workshop_scoped(self) -> None:
        request = RequestFactory().post("/", {"legal_confirmation": "on"})
        request.user = self.user
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=False), patch("apps.finance.views.nfe_credit.create_and_emit_nfe_credit_type_one") as service:
            with self.assertRaises(Exception):
                NfeCreditIssueView.as_view()(request, pk=self.preview.pk)
        service.assert_not_called()
        document = self.emit()
        get_request = RequestFactory().get("/")
        get_request.user = self.user
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=True):
            response = NfeCreditPayloadView.as_view()(get_request, pk=document.pk)
        self.assertNotIn("secret", response.content.decode())


class FiscalPhaseTwoCreditTypeOneConcurrentTests(CreditFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def setUp(self) -> None:
        self.preview = self.build_fixture(suffix=72)

    def test_concurrent_same_preview_calls_remote_once(self) -> None:
        barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[str] = []
        lock = threading.Lock()

        def delayed_response(*args: Any, **kwargs: Any) -> Mock:
            time.sleep(0.1)
            return _response(self.success_payload())

        def run() -> None:
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                preview = FiscalCreditProductPreview.objects.get(pk=self.preview.pk)
                workshop = Workshop.objects.get(pk=self.workshop.pk)
                user = User.objects.get(pk=self.user.pk)
                create_and_emit_nfe_credit_type_one(preview=preview, workshop=workshop, requested_by=user, legal_confirmation=True)
            except Exception as exc:
                with lock:
                    errors.append(str(exc))
            else:
                with lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with patch("apps.finance.services.nfe_credit._build_headers", return_value={}), patch("apps.finance.services.nfe_credit.requests.post", side_effect=delayed_response) as post:
            threads = [threading.Thread(target=run), threading.Thread(target=run)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)
        self.assertEqual(post.call_count, 1, errors)
        self.assertEqual(results, ["sent"], errors)
        self.assertEqual(len(errors), 1)
        self.assertEqual(FiscalDocument.objects.filter(credit_product_preview=self.preview).count(), 1)
