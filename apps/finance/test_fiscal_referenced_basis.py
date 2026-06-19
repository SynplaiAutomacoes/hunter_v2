from __future__ import annotations

from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import RequestFactory, TestCase

from apps.accounts.models import Account, User
from apps.budget.models import Budget, BudgetStatus
from apps.finance.models.finance import (
    FiscalDocument,
    FiscalDocumentOrigin,
    FiscalDocumentPurpose,
    FiscalDocumentStatus,
    FiscalDocumentType,
    FiscalEmissionAttempt,
    FiscalEmissionOperationType,
    FiscalHypothesis,
    FiscalReferencedBasis,
    FiscalReferencedBasisStatus,
    NfeItem,
    NfeRequest,
    TaxClassNfe,
    WebmaniaCompany,
)
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.services.fiscal_referenced_basis import approve_referenced_basis, create_referenced_basis, extract_ibs_cbs_snapshot, set_credit_debit_basis_enabled, validate_hypothesis_sources
from apps.finance.views.fiscal_referenced_basis import FiscalReferencedBasisCreateView, FiscalReferencedBasisPayloadView
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def _user_and_workshop(suffix: int) -> tuple[User, Workshop]:
    user = User.objects.create_user(username=f"basis{suffix}", password="test", cpf=f"98765432{suffix:03d}")
    account = Account.objects.create(name=f"Conta Base {suffix}", owner=user)
    user.account = account
    user.is_account_owner = True
    user.save(update_fields=["account", "is_account_owner"])
    workshop = Workshop.objects.create(account=account, name=f"Oficina Base {suffix}", cnpj=f"12.345.678/0001-{suffix:02d}", phone="+5511999999999", address="Rua Base, 1")
    return user, workshop


class FiscalPhaseTwoCreditDebitBasisTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = _user_and_workshop(31)
        self.company = WebmaniaCompany.objects.create(workshop=self.workshop, credit_debit_basis_enabled=True, credit_debit_basis_enabled_by=self.user)
        budget = Budget.objects.create(workshop=self.workshop, entry_date="2026-06-19", status=BudgetStatus.APPROVED)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder)
        self.item = NfeItem.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            request=request,
            uuid="12345678-1234-4234-8234-123456789031",
            status="aprovado",
            access_key="35123456789012345678901234567890123456789031",
            raw_payload={
                "produtos": [
                    {
                        "item": 1,
                        "nome": "Peca",
                        "impostos": {"ibs_cbs": {"situacao_tributaria": "000", "classificacao_tributaria": "000001", "ibs_estadual": {"valor": "1.00"}}},
                    }
                ]
            },
        )
        self.document = FiscalDocument.objects.create(
            workshop=self.workshop,
            account=self.workshop.account,
            document_type=FiscalDocumentType.NFE,
            origin=FiscalDocumentOrigin.LOCAL,
            purpose=FiscalDocumentPurpose.NORMAL,
            legacy_nfe_item=self.item,
            remote_uuid=str(self.item.uuid),
            access_key=self.item.access_key,
            status=FiscalDocumentStatus.APPROVED,
        )

    def test_creates_local_basis_with_fiscal_sequence_and_snapshot_without_emission(self) -> None:
        basis = create_referenced_basis(
            workshop=self.workshop,
            source_document=self.document,
            source_item_sequence=1,
            fiscal_hypothesis=FiscalHypothesis.CREDIT_REFUSAL,
            created_by=self.user,
        )

        self.assertEqual(basis.status, FiscalReferencedBasisStatus.READY)
        self.assertEqual(basis.source_nfe_item, self.item)
        self.assertEqual(basis.source_item_sequence, 1)
        self.assertEqual(basis.ibs_cbs_snapshot["situacao_tributaria"], "000")
        self.assertEqual(FiscalDocument.objects.count(), 1)
        self.assertFalse(FiscalEmissionAttempt.objects.exists())

    def test_extracts_from_document_payload_before_legacy_sources(self) -> None:
        self.document.request_payload = {"produtos": [{"sequencial": 2, "impostos": {"ibs_cbs": {"situacao_tributaria": "200", "classificacao_tributaria": "200001"}}}]}
        self.document.save(update_fields=["request_payload"])
        snapshot = extract_ibs_cbs_snapshot(document=self.document, item_sequence=2)
        self.assertEqual(snapshot, {"situacao_tributaria": "200", "classificacao_tributaria": "200001"})

    def test_missing_or_incomplete_snapshot_is_blocked_without_tax_class_fallback(self) -> None:
        self.item.raw_payload = {"produtos": [{"item": 1, "impostos": {"ibs_cbs": {"situacao_tributaria": "000"}}}]}
        self.item.save(update_fields=["raw_payload"])
        TaxClassNfe.objects.create(
            workshop=self.workshop,
            reference="CURRENT",
            ibs_cbs_enabled=True,
            ibs_cbs_situacao_tributaria="999",
            ibs_cbs_classificacao_tributaria="999999",
        )
        with self.assertRaisesMessage(ValidationError, "classificacao_tributaria"):
            create_referenced_basis(
                workshop=self.workshop,
                source_document=self.document,
                source_item_sequence=1,
                fiscal_hypothesis=FiscalHypothesis.CREDIT_REFUSAL,
                created_by=self.user,
            )
        self.assertFalse(FiscalReferencedBasis.objects.exists())

    def test_approved_snapshot_is_immutable(self) -> None:
        basis = create_referenced_basis(workshop=self.workshop, source_document=self.document, source_item_sequence=1, fiscal_hypothesis=FiscalHypothesis.CREDIT_REFUSAL, created_by=self.user, notes="Recusa registrada para revisao fiscal.")
        basis = approve_referenced_basis(basis=basis, approved_by=self.user)
        basis.ibs_cbs_snapshot = {"situacao_tributaria": "999", "classificacao_tributaria": "999999"}
        with self.assertRaisesMessage(ValidationError, "imutavel"):
            basis.save()

    def test_financial_and_stock_hypotheses_require_real_references(self) -> None:
        with self.assertRaisesMessage(ValidationError, "movimentacao financeira"):
            validate_hypothesis_sources(hypothesis=FiscalHypothesis.DEBIT_ADVANCE_PAYMENT, financial_reference=None, stock_reference=None)
        with self.assertRaisesMessage(ValidationError, "movimentacao de estoque"):
            validate_hypothesis_sources(hypothesis=FiscalHypothesis.DEBIT_STOCK_LOSS, financial_reference=None, stock_reference=None)
        with self.assertRaisesMessage(ValidationError, "desconhecida"):
            validate_hypothesis_sources(hypothesis="unknown", financial_reference=None, stock_reference=None)

    def test_valid_financial_hypothesis_can_prepare_basis_but_not_emit(self) -> None:
        movement = FinancialMovement.objects.create(workshop=self.workshop, user=self.user, direction=FinancialMovement.MovementDirection.CREDIT)
        basis = create_referenced_basis(
            workshop=self.workshop,
            source_document=self.document,
            source_item_sequence=1,
            fiscal_hypothesis=FiscalHypothesis.CREDIT_FINE_INTEREST,
            financial_reference=movement,
            created_by=self.user,
        )
        self.assertEqual(basis.financial_reference, movement)
        self.assertFalse(FiscalEmissionAttempt.objects.exists())

    def test_disabled_feature_blocks_preparation_and_toggle_is_audited(self) -> None:
        set_credit_debit_basis_enabled(workshop=self.workshop, enabled=False, actor=self.user)
        self.company.refresh_from_db()
        self.assertFalse(self.company.credit_debit_basis_enabled)
        self.assertEqual(self.company.credit_debit_basis_enabled_by, self.user)
        self.assertIsNotNone(self.company.credit_debit_basis_enabled_at)
        with self.assertRaisesMessage(ValidationError, "nao esta habilitada"):
            create_referenced_basis(workshop=self.workshop, source_document=self.document, source_item_sequence=1, fiscal_hypothesis=FiscalHypothesis.CREDIT_REFUSAL, created_by=self.user)

    def test_feature_flag_does_not_enable_credit_or_debit_emission_operations(self) -> None:
        self.assertNotIn("nfe_credit_emission", FiscalEmissionOperationType.values)
        self.assertNotIn("nfe_debit_emission", FiscalEmissionOperationType.values)

    def test_cross_workshop_document_and_reference_are_blocked(self) -> None:
        other_user, other_workshop = _user_and_workshop(32)
        WebmaniaCompany.objects.create(workshop=other_workshop, credit_debit_basis_enabled=True)
        with self.assertRaises(FiscalDocument.DoesNotExist):
            create_referenced_basis(workshop=other_workshop, source_document=self.document, source_item_sequence=1, fiscal_hypothesis=FiscalHypothesis.CREDIT_REFUSAL, created_by=other_user)

    def test_external_basis_without_validated_xml_cannot_be_approved(self) -> None:
        external_document = FiscalDocument.objects.create(
            workshop=self.workshop,
            account=self.workshop.account,
            document_type=FiscalDocumentType.NFE,
            origin=FiscalDocumentOrigin.EXTERNAL,
            purpose=FiscalDocumentPurpose.NORMAL,
            access_key="35123456789012345678901234567890123456789032",
            status=FiscalDocumentStatus.APPROVED,
            external_confirmation=True,
        )
        basis = FiscalReferencedBasis.objects.create(
            workshop=self.workshop,
            source_document=external_document,
            source_access_key="35123456789012345678901234567890123456789032",
            source_item_sequence=1,
            basis_type="credit",
            fiscal_hypothesis=FiscalHypothesis.CREDIT_REFUSAL,
            ibs_cbs_snapshot={"situacao_tributaria": "000", "classificacao_tributaria": "000001"},
            external_origin=True,
            external_xml_validated=False,
            status=FiscalReferencedBasisStatus.READY,
            created_by=self.user,
            notes="Documento externo aguardando validacao XML.",
        )
        with self.assertRaisesMessage(ValidationError, "XML/importacao validada"):
            approve_referenced_basis(basis=basis, approved_by=self.user)

    def test_basis_type_must_match_hypothesis(self) -> None:
        with self.assertRaisesMessage(ValidationError, "nao corresponde"):
            FiscalReferencedBasis.objects.create(
                workshop=self.workshop,
                source_document=self.document,
                source_access_key=self.document.access_key,
                source_item_sequence=1,
                basis_type="debit",
                fiscal_hypothesis=FiscalHypothesis.CREDIT_REFUSAL,
                ibs_cbs_snapshot={"situacao_tributaria": "000", "classificacao_tributaria": "000001"},
            )

    def test_payload_view_requires_specific_permission_and_sanitizes(self) -> None:
        basis = create_referenced_basis(workshop=self.workshop, source_document=self.document, source_item_sequence=1, fiscal_hypothesis=FiscalHypothesis.CREDIT_REFUSAL, created_by=self.user)
        request = RequestFactory().get("/")
        request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
        ):
            with self.assertRaises(PermissionDenied):
                FiscalReferencedBasisPayloadView.as_view()(request, pk=basis.pk)

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            response = FiscalReferencedBasisPayloadView.as_view()(request, pk=basis.pk)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("consumer_secret", response.content.decode())

        _other_user, other_workshop = _user_and_workshop(33)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                FiscalReferencedBasisPayloadView.as_view()(request, pk=basis.pk)

    def test_create_view_without_permission_never_reaches_service(self) -> None:
        request = RequestFactory().post("/", data={})
        request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
            patch("apps.finance.views.fiscal_referenced_basis.create_referenced_basis") as service_mock,
        ):
            with self.assertRaises(PermissionDenied):
                FiscalReferencedBasisCreateView.as_view()(request)
        service_mock.assert_not_called()
