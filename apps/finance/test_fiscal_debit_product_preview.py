from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import RequestFactory, TestCase

from apps.accounts.models import Account, User
from apps.budget.models import Budget, BudgetStatus
from apps.finance.models.finance import (
    FiscalCreditProductPreview,
    FiscalDebitProductPreview,
    FiscalDocument,
    FiscalDocumentOrigin,
    FiscalDocumentPurpose,
    FiscalDocumentStatus,
    FiscalDocumentType,
    FiscalEmissionAttempt,
    FiscalEmissionOperationType,
    FiscalHypothesis,
    FiscalReferencedBasis,
    FiscalReferencedBasisItem,
    NfeItem,
    NfeRequest,
    TaxClassNfe,
    WebmaniaCompany,
)
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.services.fiscal_debit_product_preview import approve_debit_product_preview, create_debit_product_preview, detect_forbidden_debit_groups
from apps.finance.services.fiscal_referenced_basis import approve_referenced_basis, create_referenced_basis
from apps.finance.views.fiscal_debit_product_preview import FiscalDebitProductPreviewApproveView, FiscalDebitProductPreviewCreateView, FiscalDebitProductPreviewPayloadView
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def _scope(suffix: int) -> tuple[User, Workshop]:
    user = User.objects.create_user(username=f"debitpreview{suffix}", password="test", cpf=f"76543210{suffix:03d}")
    account = Account.objects.create(name=f"Conta Debit Prévia {suffix}", owner=user)
    user.account = account
    user.is_account_owner = True
    user.save(update_fields=["account", "is_account_owner"])
    workshop = Workshop.objects.create(account=account, name=f"Oficina Debit Prévia {suffix}", cnpj=f"32.345.678/0001-{suffix:02d}", phone="+5511999999999", address="Rua Debit Prévia, 1")
    return user, workshop


class FiscalPhaseTwoDebitProductPreviewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = _scope(61)
        self.company = WebmaniaCompany.objects.create(workshop=self.workshop, credit_debit_basis_enabled=True, credit_debit_basis_enabled_by=self.user)
        budget = Budget.objects.create(workshop=self.workshop, entry_date="2026-06-22", status=BudgetStatus.APPROVED)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder)
        self.nfe_item = NfeItem.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            request=request,
            uuid="22345678-1234-4234-8234-123456789061",
            status="aprovado",
            access_key="35123456789012345678901234567890123456789061",
            raw_payload={
                "produtos": [
                    {
                        "item": 1,
                        "nome": "Peca historica débito",
                        "codigo": "DEBIT-HIST-1",
                        "ncm": "87089990",
                        "codigo_cfop": "5102",
                        "quantidade": "2.000000",
                        "unidade": "UN",
                        "subtotal": "50.00",
                        "total": "100.00",
                        "impostos": {"ibs_cbs": {"situacao_tributaria": "800", "classificacao_tributaria": "800001", "ibs_estadual": {"valor": "1.00"}}},
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
            legacy_nfe_item=self.nfe_item,
            remote_uuid=str(self.nfe_item.uuid),
            access_key=self.nfe_item.access_key,
            status=FiscalDocumentStatus.APPROVED,
        )
        movement = FinancialMovement.objects.create(workshop=self.workshop, user=self.user, direction=FinancialMovement.MovementDirection.CREDIT)
        basis = create_referenced_basis(
            workshop=self.workshop,
            source_document=self.document,
            source_item_sequence=1,
            fiscal_hypothesis=FiscalHypothesis.DEBIT_FINE_INTEREST,
            financial_reference=movement,
            created_by=self.user,
            notes="Multa e juros validados para prévia de débito.",
            fine_amount=Decimal("5.00"),
            interest_amount=Decimal("2.00"),
        )
        self.basis = approve_referenced_basis(basis=basis, approved_by=self.user)

    def create_preview(self, **overrides) -> FiscalDebitProductPreview:
        data = {
            "workshop": self.workshop,
            "basis": self.basis,
            "referenced_access_key": self.basis.source_access_key,
            "referenced_item_sequence": self.basis.source_item_sequence,
            "quantity": Decimal("2.000000"),
            "unit_price": Decimal("3.50"),
            "total_amount": Decimal("7.00"),
            "cfop": "5102",
            "created_by": self.user,
            "explicit_value_confirmation": True,
        }
        data.update(overrides)
        return create_debit_product_preview(**data)

    def test_creates_debit_preview_with_required_reference_without_remote_entities(self) -> None:
        with patch("requests.post") as post:
            preview = self.create_preview()

        self.assertEqual(preview.operation_type, "debit")
        self.assertEqual(preview.fiscal_purpose_type, "4")
        self.assertEqual(preview.dfe_referenciado, {"chave": self.document.access_key, "item": 1})
        self.assertEqual(preview.preview_payload["finalidade"], 6)
        self.assertEqual(preview.preview_payload["tipo_debito"], 4)
        self.assertEqual(preview.product_payload["dfe_referenciado"], preview.dfe_referenciado)
        self.assertEqual(FiscalDocument.objects.count(), 1)
        self.assertFalse(FiscalEmissionAttempt.objects.exists())
        self.assertFalse(FiscalDocument.objects.filter(purpose="debit").exists())
        post.assert_not_called()

    def test_product_uses_explicit_values_and_only_approved_snapshots(self) -> None:
        preview = self.create_preview(quantity=Decimal("4.000000"), unit_price=Decimal("1.75"), total_amount=Decimal("7.00"), cfop="6102")
        product = preview.product_payload
        self.assertEqual(product["nome"], "Peca historica débito")
        self.assertEqual(product["quantidade"], "4.000000")
        self.assertEqual(product["subtotal"], "1.75")
        self.assertEqual(product["total"], "7.00")
        self.assertEqual(product["codigo_cfop"], "6102")
        self.assertEqual(set(product["impostos"]), {"ibs_cbs"})
        self.assertEqual(preview.ibs_cbs_payload, self.basis.ibs_cbs_snapshot)

    def test_unapproved_basis_or_missing_item_is_blocked(self) -> None:
        FiscalReferencedBasis.objects.filter(pk=self.basis.pk).update(status="ready")
        self.basis.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "base fiscal aprovada"):
            self.create_preview()
        FiscalReferencedBasis.objects.filter(pk=self.basis.pk).update(status="approved")
        FiscalReferencedBasisItem.objects.filter(pk=self.basis.commercial_item.pk).delete()
        self.basis.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "não possui item"):
            self.create_preview()

    def test_credit_basis_cannot_be_used_as_debit_preview(self) -> None:
        FiscalReferencedBasis.objects.filter(pk=self.basis.pk).update(fiscal_hypothesis=FiscalHypothesis.CREDIT_FINE_INTEREST, basis_type="credit")
        self.basis.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "somente débito tipo 4"):
            self.create_preview()
        self.assertFalse(FiscalCreditProductPreview.objects.exists())

    def test_dfe_reference_must_match_approved_basis(self) -> None:
        with self.assertRaisesMessage(ValidationError, "chave do DF-e referenciado"):
            self.create_preview(referenced_access_key="")
        with self.assertRaisesMessage(ValidationError, "item do DF-e referenciado"):
            self.create_preview(referenced_item_sequence=2)

    def test_explicit_positive_values_and_consistent_total_are_required(self) -> None:
        for field, value in (("quantity", Decimal("0")), ("unit_price", Decimal("0")), ("total_amount", Decimal("0"))):
            with self.subTest(field=field), self.assertRaisesMessage(ValidationError, "devem ser positivos"):
                self.create_preview(**{field: value})
        with self.assertRaisesMessage(ValidationError, "definidos explicitamente"):
            self.create_preview(explicit_value_confirmation=False)
        with self.assertRaisesMessage(ValidationError, "Quantidade x valor unitário"):
            self.create_preview(unit_price=Decimal("3.00"))
        with self.assertRaisesMessage(ValidationError, "multa + juros"):
            self.create_preview(quantity=Decimal("1"), unit_price=Decimal("8.00"), total_amount=Decimal("8.00"))

    def test_missing_cfop_or_ibs_cbs_is_blocked_without_current_fallbacks(self) -> None:
        with self.assertRaisesMessage(ValidationError, "CFOP"):
            self.create_preview(cfop="")
        TaxClassNfe.objects.create(workshop=self.workshop, reference="CURRENT-DEBIT", ibs_cbs_enabled=True, ibs_cbs_situacao_tributaria="999", ibs_cbs_classificacao_tributaria="999999")
        FiscalReferencedBasis.objects.filter(pk=self.basis.pk).update(ibs_cbs_snapshot={})
        self.basis.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "Snapshot IBS/CBS insuficiente"):
            self.create_preview()

    def test_missing_historical_product_data_is_blocked_without_product_fallback(self) -> None:
        FiscalReferencedBasisItem.objects.filter(pk=self.basis.commercial_item.pk).update(source_item_description="")
        self.basis.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "Snapshot comercial insuficiente"):
            self.create_preview()

    def test_forbidden_tax_and_credit_fields_are_detected_and_blocked(self) -> None:
        malicious = {
            "dfe_referenciado": {"chave": self.basis.source_access_key, "item": 1},
            "impostos": {"ibs_cbs": self.basis.ibs_cbs_snapshot, "icms": {"situacao_tributaria": "00"}},
            "tipo_credito": 1,
        }
        self.assertEqual(detect_forbidden_debit_groups(malicious), ["impostos.icms", "tipo_credito"])
        with patch("apps.finance.services.fiscal_debit_product_preview._build_debit_product_payload", return_value=(malicious, self.basis.ibs_cbs_snapshot)):
            with self.assertRaisesMessage(ValidationError, "grupos proibidos"):
                self.create_preview()

    def test_approved_preview_is_immutable_and_independent_from_credit_preview(self) -> None:
        preview = approve_debit_product_preview(preview=self.create_preview(), approved_by=self.user)
        preview.product_total_amount = Decimal("8.00")
        preview.dfe_referenciado["item"] = 2
        with self.assertRaisesMessage(ValidationError, "imutáveis"):
            preview.save()
        self.assertFalse(FiscalCreditProductPreview.objects.exists())

    def test_disabled_preparation_flag_blocks_preview_without_emitting(self) -> None:
        self.company.credit_debit_basis_enabled = False
        self.company.save(update_fields=["credit_debit_basis_enabled"])
        with self.assertRaisesMessage(ValidationError, "desabilitada"):
            self.create_preview()
        self.assertIn("nfe_debit_emission", FiscalEmissionOperationType.values)
        self.assertFalse(FiscalEmissionAttempt.objects.exists())
        self.assertFalse(FiscalDocument.objects.filter(purpose=FiscalDocumentPurpose.DEBIT).exists())

    def test_cross_workshop_is_blocked(self) -> None:
        other_user, other_workshop = _scope(62)
        WebmaniaCompany.objects.create(workshop=other_workshop, credit_debit_basis_enabled=True)
        with self.assertRaises(FiscalReferencedBasis.DoesNotExist):
            self.create_preview(workshop=other_workshop, created_by=other_user)

    def test_debit_permissions_are_required_and_credit_permission_is_not_enough(self) -> None:
        request = RequestFactory().post("/", data={})
        request.user = self.user

        def credit_only_permission(*args, **kwargs):
            return kwargs.get("codename", "").startswith(("prepare_nfe_credit", "approve_nfe_credit"))

        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", side_effect=credit_only_permission),
            patch("apps.finance.views.fiscal_debit_product_preview.create_debit_product_preview") as service_mock,
        ):
            with self.assertRaises(PermissionDenied):
                FiscalDebitProductPreviewCreateView.as_view()(request)
        service_mock.assert_not_called()

        preview = self.create_preview()
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", side_effect=credit_only_permission),
            patch("apps.finance.views.fiscal_debit_product_preview.approve_debit_product_preview") as approve_mock,
        ):
            with self.assertRaises(PermissionDenied):
                FiscalDebitProductPreviewApproveView.as_view()(request, pk=preview.pk)
        approve_mock.assert_not_called()

    def test_payload_view_requires_permission_sanitizes_and_scopes_workshop(self) -> None:
        preview = self.create_preview()
        preview.preview_payload["consumer_secret"] = "secret"
        preview.save(update_fields=["preview_payload", "atualizado_em"])
        request = RequestFactory().get("/")
        request.user = self.user
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=False):
            with self.assertRaises(PermissionDenied):
                FiscalDebitProductPreviewPayloadView.as_view()(request, pk=preview.pk)
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=True):
            response = FiscalDebitProductPreviewPayloadView.as_view()(request, pk=preview.pk)
        self.assertNotIn('"consumer_secret": "secret"', response.content.decode())
        self.assertIn("[REDACTED]", response.content.decode())
        _other_user, other_workshop = _scope(63)
        with patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop), patch("apps.workshops.mixin.has_workshop_perm", return_value=True):
            with self.assertRaises(Http404):
                FiscalDebitProductPreviewPayloadView.as_view()(request, pk=preview.pk)
