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
    FiscalDebitProductPreview,
    FiscalDocument,
    FiscalDocumentLink,
    FiscalDocumentLinkRole,
    FiscalDocumentOrigin,
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
from apps.finance.services.nfe_debit import NfeDebitError, create_and_emit_nfe_debit_type_four, reconcile_nfe_debit_document, set_nfe_debit_emission_enabled
from apps.finance.services.webmania_documents import DownloadedWebmaniaDocument
from apps.finance.services.webmania_webhooks import process_webhook_event
from apps.finance.views.nfe_debit import NfeDebitDownloadView, NfeDebitIssueView, NfeDebitPayloadView
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def _response(payload: dict[str, Any]) -> Mock:
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


class DebitFixtureMixin:
    def build_fixture(self, *, suffix: int = 81) -> FiscalDebitProductPreview:
        self.user = User.objects.create_user(username=f"debit{suffix}", password="test", cpf=f"65432109{suffix:03d}")
        account = Account.objects.create(name=f"Conta Debito {suffix}", owner=self.user)
        self.user.account = account
        self.user.is_account_owner = True
        self.user.save(update_fields=["account", "is_account_owner"])
        self.workshop = Workshop.objects.create(account=account, name=f"Oficina Debito {suffix}", cnpj=f"43.345.678/0001-{suffix:02d}", phone="+5511999999999", address="Rua Debito, 1")
        WebmaniaCompany.objects.create(workshop=self.workshop, credit_debit_basis_enabled=True, nfe_debit_emission_enabled=True)
        customer = Customer.objects.create(workshop=self.workshop, customer_type="PF", name="Cliente Debito", cpf_or_cnpj="12345678901", email="debito@example.test", logradouro="Rua Teste", numero="123", bairro="Centro", cidade="Sao Paulo", estado="SP", cep="01001-000")
        budget = Budget.objects.create(workshop=self.workshop, entry_date="2026-06-22", status=BudgetStatus.APPROVED, customer=customer)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder)
        nfe_item = NfeItem.objects.create(workshop=self.workshop, workorder=workorder, request=nfe_request, uuid=f"32345678-1234-4234-8234-123456789{suffix:03d}"[-36:], status="aprovado", access_key=f"35{suffix:042d}"[-44:], raw_payload={"produtos": [{"item": 1}]})
        source = FiscalDocument.objects.create(workshop=self.workshop, account=account, legacy_nfe_item=nfe_item, remote_uuid=str(nfe_item.uuid), access_key=nfe_item.access_key, status=FiscalDocumentStatus.APPROVED)
        basis = FiscalReferencedBasis.objects.create(workshop=self.workshop, source_document=source, source_nfe_item=nfe_item, source_access_key=nfe_item.access_key, source_item_sequence=1, basis_type="debit", fiscal_hypothesis="debit_fine_interest", ibs_cbs_snapshot={"situacao_tributaria": "800", "classificacao_tributaria": "800001"}, status=FiscalReferencedBasisStatus.APPROVED, approved_by=self.user)
        item = FiscalReferencedBasisItem.objects.create(basis=basis, source_item_sequence=1, source_item_description="Multa e juros debito", source_item_code="MJD-1", source_item_ncm="00000000", source_item_cfop="5949", source_quantity=Decimal("1"), source_unit="UN", source_unit_price=Decimal("7"), source_total_amount=Decimal("7"), fine_amount=Decimal("5"), interest_amount=Decimal("2"), credit_debit_base_amount=Decimal("7"), commercial_snapshot={"source": "xml"}, monetary_snapshot={"fine": "5", "interest": "2"})
        dfe_reference = {"chave": nfe_item.access_key, "item": 1}
        product = {"nome": "Multa e juros debito", "codigo": "MJD-1", "ncm": "00000000", "quantidade": "1.000000", "unidade": "UN", "subtotal": "7.00", "total": "7.00", "codigo_cfop": "5949", "dfe_referenciado": dfe_reference, "impostos": {"ibs_cbs": basis.ibs_cbs_snapshot}}
        return FiscalDebitProductPreview.objects.create(workshop=self.workshop, basis=basis, basis_item=item, revision=1, source_access_key=nfe_item.access_key, source_item_sequence=1, dfe_referenciado=dfe_reference, product_cfop="5949", product_quantity=Decimal("1"), product_unit_price=Decimal("7"), product_total_amount=Decimal("7"), product_payload=product, ibs_cbs_payload=basis.ibs_cbs_snapshot, preview_payload={"modelo": 1, "finalidade": 6, "tipo_debito": 4, "produtos": [product]}, validation_status=FiscalProductPreviewStatus.APPROVED, explicit_value_confirmation=True, created_by=self.user, approved_by=self.user)

    @staticmethod
    def success_payload() -> dict[str, Any]:
        return {"uuid": "42345678-1234-4234-8234-123456789081", "modelo": "nfe", "status": "aprovado", "nfe": "8001", "serie": "1", "recibo": "REC-DEBIT", "chave": "35123456789012345678901234567890123456789081", "xml": "https://example.test/debit.xml", "danfe": "https://example.test/debit.pdf", "log": {"token": "secret"}}


class FiscalPhaseTwoDebitTypeFourTests(DebitFixtureMixin, TestCase):
    def setUp(self) -> None:
        self.preview = self.build_fixture()

    def emit(self, **kwargs: Any) -> FiscalDocument:
        data = {"preview": self.preview, "workshop": self.workshop, "requested_by": self.user, "legal_confirmation": True}
        data.update(kwargs)
        with patch("apps.finance.services.nfe_debit._build_headers", return_value={}), patch("apps.finance.services.nfe_debit.requests.post", return_value=_response(self.success_payload())) as post:
            document = create_and_emit_nfe_debit_type_four(**data)
        self.post_mock = post
        return document

    def test_contract_uses_preview_reference_and_only_ibs_cbs(self) -> None:
        document = self.emit()
        payload = self.post_mock.call_args.kwargs["json"]
        self.assertEqual((payload["modelo"], payload["finalidade"], payload["tipo_debito"]), (1, 6, 4))
        self.assertNotIn("nfe_referenciada", payload)
        self.assertEqual(payload["produtos"], [self.preview.product_payload])
        self.assertEqual(payload["produtos"][0]["dfe_referenciado"], self.preview.dfe_referenciado)
        self.assertEqual(payload["produtos"][0]["codigo_cfop"], "5949")
        self.assertEqual(set(payload["produtos"][0]["impostos"]), {"ibs_cbs"})
        forbidden = {"tipo_credito", "nfe_credito", "cod_evento", "evento_ibs_cbs", "imposto_devolvido"}
        self.assertFalse(forbidden.intersection(payload))
        self.assertFalse({"icms", "ipi", "pis", "cofins", "issqn", "ii"}.intersection(payload["produtos"][0]["impostos"]))
        self.assertIn("cliente", payload)
        self.assertIn("pedido", payload)
        self.assertEqual(document.purpose, FiscalDocumentPurpose.DEBIT)

    def test_model_links_preview_basis_and_original_without_mutating_sources(self) -> None:
        source_status = self.preview.basis.source_document.status
        preview_payload = dict(self.preview.product_payload)
        basis_status = self.preview.basis.status
        document = self.emit()
        self.assertEqual(document.fiscal_purpose_type, "4")
        self.assertEqual(document.referenced_basis, self.preview.basis)
        self.assertEqual(document.debit_product_preview, self.preview)
        link = FiscalDocumentLink.objects.get(document=document)
        self.assertEqual(link.role, FiscalDocumentLinkRole.DEBITS)
        self.preview.refresh_from_db()
        self.preview.basis.refresh_from_db()
        self.preview.basis.source_document.refresh_from_db()
        self.assertEqual(self.preview.product_payload, preview_payload)
        self.assertEqual(self.preview.basis.status, basis_status)
        self.assertEqual(self.preview.basis.source_document.status, source_status)

    def test_document_and_attempt_exist_before_gateway_and_payload_is_frozen(self) -> None:
        def inspect_before_response(*args: Any, **kwargs: Any) -> Mock:
            document = FiscalDocument.objects.get(debit_product_preview=self.preview)
            attempt = FiscalEmissionAttempt.objects.get(fiscal_document=document)
            self.assertEqual(attempt.operation_type, FiscalEmissionOperationType.NFE_DEBIT_EMISSION)
            self.assertEqual(attempt.request_payload, kwargs["json"])
            return _response(self.success_payload())

        with patch("apps.finance.services.nfe_debit._build_headers", return_value={}), patch("apps.finance.services.nfe_debit.requests.post", side_effect=inspect_before_response):
            document = create_and_emit_nfe_debit_type_four(preview=self.preview, workshop=self.workshop, requested_by=self.user, legal_confirmation=True)
        self.assertEqual(document.emission_attempts.get().request_payload, document.request_payload)

    def test_retry_same_preview_is_blocked_without_remote_call(self) -> None:
        self.emit()
        with patch("apps.finance.services.nfe_debit.requests.post") as post, self.assertRaisesMessage(NfeDebitError, "ja possui"):
            create_and_emit_nfe_debit_type_four(preview=self.preview, workshop=self.workshop, requested_by=self.user, legal_confirmation=True)
        post.assert_not_called()

    def test_timeout_marks_uncertain_and_blocks_retry(self) -> None:
        with patch("apps.finance.services.nfe_debit._build_headers", return_value={}), patch("apps.finance.services.nfe_debit.requests.post", side_effect=requests.Timeout), self.assertRaisesMessage(NfeDebitError, "incerto"):
            create_and_emit_nfe_debit_type_four(preview=self.preview, workshop=self.workshop, requested_by=self.user, legal_confirmation=True)
        document = FiscalDocument.objects.get(debit_product_preview=self.preview)
        self.assertEqual(document.status, FiscalDocumentStatus.UNCERTAIN)
        self.assertEqual(document.emission_attempts.get().status, FiscalEmissionAttemptStatus.UNCERTAIN)
        with patch("apps.finance.services.nfe_debit.requests.post") as post, self.assertRaises(NfeDebitError):
            create_and_emit_nfe_debit_type_four(preview=self.preview, workshop=self.workshop, requested_by=self.user, legal_confirmation=True)
        post.assert_not_called()

    def test_eligibility_blocks_draft_base_flag_cross_workshop_and_external_origin(self) -> None:
        FiscalDebitProductPreview.objects.filter(pk=self.preview.pk).update(validation_status=FiscalProductPreviewStatus.DRAFT)
        self.preview.refresh_from_db()
        with self.assertRaisesMessage(NfeDebitError, "aprovada"):
            self.emit()
        FiscalDebitProductPreview.objects.filter(pk=self.preview.pk).update(validation_status=FiscalProductPreviewStatus.APPROVED)
        FiscalReferencedBasis.objects.filter(pk=self.preview.basis_id).update(status=FiscalReferencedBasisStatus.READY)
        self.preview.refresh_from_db()
        with self.assertRaisesMessage(NfeDebitError, "base fiscal"):
            self.emit()
        FiscalReferencedBasis.objects.filter(pk=self.preview.basis_id).update(status=FiscalReferencedBasisStatus.APPROVED)
        WebmaniaCompany.objects.filter(workshop=self.workshop).update(nfe_debit_emission_enabled=False, credit_debit_basis_enabled=True)
        self.preview.refresh_from_db()
        with self.assertRaisesMessage(NfeDebitError, "desabilitada"):
            self.emit()
        WebmaniaCompany.objects.filter(workshop=self.workshop).update(nfe_debit_emission_enabled=True)
        FiscalDocument.objects.filter(pk=self.preview.basis.source_document_id).update(origin=FiscalDocumentOrigin.EXTERNAL)
        self.preview.refresh_from_db()
        with self.assertRaisesMessage(NfeDebitError, "original local"):
            self.emit()
        other_preview = self.build_fixture(suffix=83)
        with self.assertRaises(FiscalDebitProductPreview.DoesNotExist):
            create_and_emit_nfe_debit_type_four(preview=self.preview, workshop=self.workshop, requested_by=self.user, legal_confirmation=True)
        self.assertNotEqual(other_preview.workshop_id, self.preview.workshop_id)

    def test_missing_reference_forbidden_tax_or_zero_total_is_blocked(self) -> None:
        product = dict(self.preview.product_payload)
        product.pop("dfe_referenciado")
        FiscalDebitProductPreview.objects.filter(pk=self.preview.pk).update(product_payload=product)
        self.preview.refresh_from_db()
        with self.assertRaisesMessage(NfeDebitError, "dfe_referenciado"):
            self.emit()
        product["dfe_referenciado"] = self.preview.dfe_referenciado
        product["impostos"]["icms"] = {"cst": "00"}
        FiscalDebitProductPreview.objects.filter(pk=self.preview.pk).update(product_payload=product)
        self.preview.refresh_from_db()
        with self.assertRaisesMessage(NfeDebitError, "proibidos"):
            self.emit()
        product["impostos"] = {"ibs_cbs": self.preview.ibs_cbs_payload}
        FiscalDebitProductPreview.objects.filter(pk=self.preview.pk).update(product_payload=product, ibs_cbs_payload={})
        self.preview.refresh_from_db()
        with self.assertRaisesMessage(NfeDebitError, "IBS/CBS"):
            self.emit()
        FiscalDebitProductPreview.objects.filter(pk=self.preview.pk).update(ibs_cbs_payload=self.preview.basis.ibs_cbs_snapshot)
        FiscalReferencedBasisItem.objects.filter(pk=self.preview.basis_item_id).update(credit_debit_base_amount=Decimal("0"))
        self.preview.refresh_from_db()
        with self.assertRaisesMessage(NfeDebitError, "positivo"):
            self.emit()

    def test_source_document_and_frozen_snapshots_must_remain_consistent(self) -> None:
        source = self.preview.basis.source_document
        FiscalDocument.objects.filter(pk=source.pk).update(status=FiscalDocumentStatus.PROCESSING)
        self.preview.refresh_from_db()
        with self.assertRaisesMessage(NfeDebitError, "original local"):
            self.emit()

        FiscalDocument.objects.filter(pk=source.pk).update(status=FiscalDocumentStatus.APPROVED, access_key="35" + ("9" * 42))
        self.preview.refresh_from_db()
        with self.assertRaisesMessage(NfeDebitError, "diverge"):
            self.emit()

        FiscalDocument.objects.filter(pk=source.pk).update(access_key=self.preview.source_access_key)
        FiscalReferencedBasisItem.objects.filter(pk=self.preview.basis_item_id).update(commercial_snapshot={})
        self.preview.refresh_from_db()
        with self.assertRaisesMessage(NfeDebitError, "snapshots"):
            self.emit()

        FiscalReferencedBasisItem.objects.filter(pk=self.preview.basis_item_id).update(commercial_snapshot={"source": "xml"})
        product = dict(self.preview.product_payload)
        product["total"] = "8.00"
        FiscalDebitProductPreview.objects.filter(pk=self.preview.pk).update(product_payload=product)
        self.preview.refresh_from_db()
        with self.assertRaisesMessage(NfeDebitError, "valores congelados"):
            self.emit()

    def test_rejected_response_with_xml_does_not_become_success(self) -> None:
        rejected = {**self.success_payload(), "status": "reprovado", "motivo": "Rejeicao fiscal", "xml": "https://example.test/rejected.xml"}
        with patch("apps.finance.services.nfe_debit._build_headers", return_value={}), patch("apps.finance.services.nfe_debit.requests.post", return_value=_response(rejected)), self.assertRaisesMessage(NfeDebitError, "rejeitada"):
            create_and_emit_nfe_debit_type_four(preview=self.preview, workshop=self.workshop, requested_by=self.user, legal_confirmation=True)
        document = FiscalDocument.objects.get(debit_product_preview=self.preview)
        self.assertEqual(document.status, FiscalDocumentStatus.REPROVED)
        self.assertEqual(document.emission_attempts.get().status, FiscalEmissionAttemptStatus.FAILED)

    def test_webhook_updates_only_debit_document_and_is_idempotent(self) -> None:
        document = self.emit()
        source = self.preview.basis.source_document
        preview_payload = dict(self.preview.product_payload)
        payload = {**self.success_payload(), "status": "aprovado", "xml": "https://example.test/final-debit.xml"}
        event = WebmaniaWebhookEvent.objects.create(model="nfe", event_uuid=payload["uuid"], fingerprint="debit-webhook-1", payload=payload)
        self.assertTrue(process_webhook_event(event))
        self.assertTrue(process_webhook_event(event))
        document.refresh_from_db()
        source.refresh_from_db()
        self.preview.refresh_from_db()
        self.assertEqual(document.xml_url, payload["xml"])
        self.assertEqual(source.status, FiscalDocumentStatus.APPROVED)
        self.assertEqual(self.preview.product_payload, preview_payload)

    def test_ambiguous_webhook_does_not_update_any_debit_document(self) -> None:
        first_document = self.emit()
        second_preview = self.build_fixture(suffix=84)
        with patch("apps.finance.services.nfe_debit._build_headers", return_value={}), patch("apps.finance.services.nfe_debit.requests.post", return_value=_response(self.success_payload())):
            second_document = create_and_emit_nfe_debit_type_four(preview=second_preview, workshop=self.workshop, requested_by=self.user, legal_confirmation=True)
        payload = {**self.success_payload(), "status": "cancelado"}
        event = WebmaniaWebhookEvent.objects.create(model="nfe", event_uuid=payload["uuid"], fingerprint="debit-webhook-ambiguous", payload=payload)
        self.assertFalse(process_webhook_event(event))
        first_document.refresh_from_db()
        second_document.refresh_from_db()
        self.assertEqual(first_document.status, FiscalDocumentStatus.APPROVED)
        self.assertEqual(second_document.status, FiscalDocumentStatus.APPROVED)

    def test_webhook_identifier_shared_with_other_fiscal_purpose_is_ambiguous(self) -> None:
        debit_document = self.emit()
        debit_workshop = self.workshop
        other_preview = self.build_fixture(suffix=86)
        other_document = FiscalDocument.objects.create(
            workshop=other_preview.workshop,
            account=other_preview.workshop.account,
            purpose=FiscalDocumentPurpose.CREDIT,
            fiscal_purpose_type="1",
            remote_uuid=debit_document.remote_uuid,
            status=FiscalDocumentStatus.APPROVED,
        )
        payload = {**self.success_payload(), "status": "cancelado"}
        event = WebmaniaWebhookEvent.objects.create(model="nfe", event_uuid=payload["uuid"], fingerprint="debit-webhook-cross-purpose", payload=payload)

        self.assertFalse(process_webhook_event(event))
        debit_document.refresh_from_db()
        other_document.refresh_from_db()
        self.assertNotEqual(debit_workshop.pk, other_document.workshop_id)
        self.assertEqual(debit_document.status, FiscalDocumentStatus.APPROVED)
        self.assertEqual(other_document.status, FiscalDocumentStatus.APPROVED)

    def test_reconciliation_queries_without_reemitting(self) -> None:
        with patch("apps.finance.services.nfe_debit._build_headers", return_value={}), patch("apps.finance.services.nfe_debit.requests.post", side_effect=requests.Timeout), self.assertRaises(NfeDebitError):
            create_and_emit_nfe_debit_type_four(preview=self.preview, workshop=self.workshop, requested_by=self.user, legal_confirmation=True)
        document = FiscalDocument.objects.get(debit_product_preview=self.preview)
        FiscalEmissionAttempt.objects.filter(fiscal_document=document).update(remote_uuid="42345678-1234-4234-8234-123456789081")
        with patch("apps.finance.services.nfe_debit._build_headers", return_value={}), patch("apps.finance.services.nfe_debit.requests.get", return_value=_response(self.success_payload())) as get, patch("apps.finance.services.nfe_debit.requests.post") as post:
            reconciled = reconcile_nfe_debit_document(document=document)
        self.assertEqual(reconciled.status, FiscalDocumentStatus.APPROVED)
        get.assert_called_once()
        post.assert_not_called()

    def test_feature_flag_is_separate_and_audited(self) -> None:
        company = WebmaniaCompany.objects.get(workshop=self.workshop)
        company.credit_debit_basis_enabled = False
        company.save(update_fields=["credit_debit_basis_enabled"])
        set_nfe_debit_emission_enabled(workshop=self.workshop, enabled=False, actor=self.user)
        company.refresh_from_db()
        self.assertFalse(company.nfe_debit_emission_enabled)
        self.assertEqual(company.nfe_debit_emission_enabled_by, self.user)
        self.assertIsNotNone(company.nfe_debit_emission_enabled_at)

    def test_issue_payload_and_download_permissions_are_specific_and_scoped(self) -> None:
        request = RequestFactory().post("/", {"legal_confirmation": "on"})
        request.user = self.user
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=False), patch("apps.finance.views.nfe_debit.create_and_emit_nfe_debit_type_four") as service:
            with self.assertRaises(Exception):
                NfeDebitIssueView.as_view()(request, pk=self.preview.pk)
        service.assert_not_called()
        document = self.emit()
        get_request = RequestFactory().get("/")
        get_request.user = self.user
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=True):
            response = NfeDebitPayloadView.as_view()(get_request, pk=document.pk)
        self.assertNotIn("secret", response.content.decode())
        downloaded = DownloadedWebmaniaDocument(content=b"xml", content_type="application/xml", content_disposition="")
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=True), patch("apps.finance.views.nfe_debit.download_webmania_document", return_value=downloaded):
            download_response = NfeDebitDownloadView.as_view()(get_request, pk=document.pk, document="xml")
        self.assertEqual(download_response.content, b"xml")
        other_preview = self.build_fixture(suffix=85)
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=True):
            with self.assertRaises(Exception):
                NfeDebitPayloadView.as_view()(get_request, pk=FiscalDocument.objects.filter(workshop=other_preview.workshop).first().pk)


class FiscalPhaseTwoDebitTypeFourConcurrentTests(DebitFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def setUp(self) -> None:
        self.preview = self.build_fixture(suffix=82)

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
                preview = FiscalDebitProductPreview.objects.get(pk=self.preview.pk)
                workshop = Workshop.objects.get(pk=self.workshop.pk)
                user = User.objects.get(pk=self.user.pk)
                create_and_emit_nfe_debit_type_four(preview=preview, workshop=workshop, requested_by=user, legal_confirmation=True)
            except Exception as exc:
                with lock:
                    errors.append(str(exc))
            else:
                with lock:
                    results.append("sent")
            finally:
                close_old_connections()

        with patch("apps.finance.services.nfe_debit._build_headers", return_value={}), patch("apps.finance.services.nfe_debit.requests.post", side_effect=delayed_response) as post:
            threads = [threading.Thread(target=run), threading.Thread(target=run)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)
        self.assertEqual(post.call_count, 1, errors)
        self.assertEqual(results, ["sent"], errors)
        self.assertEqual(len(errors), 1)
        self.assertEqual(FiscalDocument.objects.filter(debit_product_preview=self.preview).count(), 1)
