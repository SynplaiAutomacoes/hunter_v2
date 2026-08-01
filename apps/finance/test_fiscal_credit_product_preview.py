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
    FiscalDocument,
    FiscalDocumentOrigin,
    FiscalDocumentPurpose,
    FiscalDocumentStatus,
    FiscalDocumentType,
    FiscalEmissionAttempt,
    FiscalHypothesis,
    FiscalProductPreviewStatus,
    FiscalReferencedBasis,
    FiscalReferencedBasisItem,
    NfeItem,
    NfeRequest,
    TaxClassNfe,
    WebmaniaCompany,
)
from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.services.fiscal_credit_product_preview import approve_credit_product_preview, create_credit_product_preview, detect_forbidden_groups
from apps.finance.services.fiscal_referenced_basis import approve_referenced_basis, create_referenced_basis
from apps.finance.views.fiscal_credit_product_preview import FiscalCreditProductPreviewApproveView, FiscalCreditProductPreviewCreateView, FiscalCreditProductPreviewPayloadView
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def _scope(suffix: int) -> tuple[User, Workshop]:
    user = User.objects.create_user(username=f"preview{suffix}", password="test", cpf=f"87654321{suffix:03d}")
    account = Account.objects.create(name=f"Conta Preview {suffix}", owner=user)
    user.account = account
    user.is_account_owner = True
    user.save(update_fields=["account", "is_account_owner"])
    workshop = Workshop.objects.create(account=account, name=f"Oficina Preview {suffix}", cnpj=f"22.345.678/0001-{suffix:02d}", phone="+5511999999999", address="Rua Preview, 1")
    return user, workshop


class FiscalPhaseTwoCreditProductPreviewTests(TestCase):
    def setUp(self) -> None:
        self.user, self.workshop = _scope(51)
        self.company = WebmaniaCompany.objects.create(workshop=self.workshop, credit_debit_basis_enabled=True, credit_debit_basis_enabled_by=self.user)
        budget = Budget.objects.create(workshop=self.workshop, entry_date="2026-06-22", status=BudgetStatus.APPROVED)
        workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        request = NfeRequest.objects.create(workshop=self.workshop, workorder=workorder)
        self.nfe_item = NfeItem.objects.create(
            workshop=self.workshop,
            workorder=workorder,
            request=request,
            uuid="12345678-1234-4234-8234-123456789051",
            status="aprovado",
            access_key="35123456789012345678901234567890123456789051",
            raw_payload={
                "produtos": [
                    {
                        "item": 1,
                        "nome": "Peca historica",
                        "codigo": "HIST-1",
                        "ncm": "87089990",
                        "codigo_cfop": "5102",
                        "quantidade": "2.000000",
                        "unidade": "UN",
                        "subtotal": "50.00",
                        "total": "100.00",
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
            fiscal_hypothesis=FiscalHypothesis.CREDIT_FINE_INTEREST,
            financial_reference=movement,
            created_by=self.user,
            notes="Multa e juros validados para previa.",
            fine_amount=Decimal("5.00"),
            interest_amount=Decimal("2.00"),
        )
        self.basis = approve_referenced_basis(basis=basis, approved_by=self.user)

    def create_preview(self, **overrides) -> FiscalCreditProductPreview:
        data = {
            "workshop": self.workshop,
            "basis": self.basis,
            "quantity": Decimal("2.000000"),
            "unit_price": Decimal("3.50"),
            "total_amount": Decimal("7.00"),
            "cfop": "5102",
            "created_by": self.user,
            "explicit_value_confirmation": True,
        }
        data.update(overrides)
        return create_credit_product_preview(**data)

    def test_creates_validated_preview_from_approved_basis_without_remote_entities(self) -> None:
        preview = self.create_preview()

        self.assertEqual(preview.basis, self.basis)
        self.assertEqual(preview.basis_item, self.basis.commercial_item)
        self.assertEqual(preview.validation_status, FiscalProductPreviewStatus.VALIDATED)
        self.assertEqual(preview.preview_payload["finalidade"], 5)
        self.assertEqual(preview.preview_payload["tipo_credito"], 1)
        self.assertEqual(preview.preview_payload["nfe_referenciada"], [self.document.access_key])
        self.assertEqual(preview.product_payload["total"], "7.00")
        self.assertEqual(FiscalDocument.objects.count(), 1)
        self.assertFalse(FiscalEmissionAttempt.objects.exists())
        self.assertFalse(FiscalDocument.objects.filter(purpose=FiscalDocumentPurpose.CREDIT).exists())

    def test_product_uses_explicit_values_and_historical_identity_only(self) -> None:
        preview = self.create_preview(quantity=Decimal("4.000000"), unit_price=Decimal("1.75"), total_amount=Decimal("7.00"), cfop="6102")
        product = preview.product_payload
        self.assertEqual(product["nome"], "Peca historica")
        self.assertEqual(product["quantidade"], "4.000000")
        self.assertEqual(product["subtotal"], "1.75")
        self.assertEqual(product["total"], "7.00")
        self.assertEqual(product["codigo_cfop"], "6102")

    def test_product_contains_only_ibs_cbs_tax_group(self) -> None:
        preview = self.create_preview()
        self.assertEqual(set(preview.product_payload["impostos"]), {"ibs_cbs"})
        self.assertEqual(preview.ibs_cbs_payload, self.basis.ibs_cbs_snapshot)
        self.assertEqual(preview.forbidden_tax_groups_detected, [])

    def test_unapproved_basis_is_blocked(self) -> None:
        FiscalReferencedBasis.objects.filter(pk=self.basis.pk).update(status="ready")
        self.basis.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "base fiscal aprovada"):
            self.create_preview()

    def test_approved_basis_without_item_is_blocked(self) -> None:
        FiscalReferencedBasisItem.objects.filter(pk=self.basis.commercial_item.pk).delete()
        with self.assertRaisesMessage(ValidationError, "nao possui item"):
            self.create_preview()

    def test_zero_or_missing_explicit_values_are_blocked(self) -> None:
        for field, value in (("quantity", Decimal("0")), ("unit_price", Decimal("0")), ("total_amount", Decimal("0"))):
            with self.subTest(field=field), self.assertRaisesMessage(ValidationError, "devem ser positivos"):
                self.create_preview(**{field: value})
        with self.assertRaisesMessage(ValidationError, "definidos explicitamente"):
            self.create_preview(explicit_value_confirmation=False)

    def test_inconsistent_total_or_base_amount_is_blocked(self) -> None:
        with self.assertRaisesMessage(ValidationError, "Quantidade x valor unitario"):
            self.create_preview(unit_price=Decimal("3.00"))
        with self.assertRaisesMessage(ValidationError, "multa + juros"):
            self.create_preview(quantity=Decimal("1"), unit_price=Decimal("8.00"), total_amount=Decimal("8.00"))

    def test_missing_cfop_is_blocked(self) -> None:
        with self.assertRaisesMessage(ValidationError, "CFOP"):
            self.create_preview(cfop="")

    def test_missing_ibs_cbs_is_blocked_without_tax_class_fallback(self) -> None:
        TaxClassNfe.objects.create(workshop=self.workshop, reference="CURRENT", ibs_cbs_enabled=True, ibs_cbs_situacao_tributaria="999", ibs_cbs_classificacao_tributaria="999999")
        FiscalReferencedBasis.objects.filter(pk=self.basis.pk).update(ibs_cbs_snapshot={})
        self.basis.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "Snapshot IBS/CBS insuficiente"):
            self.create_preview()

    def test_missing_historical_product_data_is_blocked_without_current_product_fallback(self) -> None:
        FiscalReferencedBasisItem.objects.filter(pk=self.basis.commercial_item.pk).update(source_item_description="")
        self.basis.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "Snapshot comercial insuficiente"):
            self.create_preview()

    def test_forbidden_tax_groups_are_detected_and_blocked(self) -> None:
        malicious = {"impostos": {"ibs_cbs": self.basis.ibs_cbs_snapshot, "icms": {"situacao_tributaria": "00"}}, "tipo_debito": 4}
        self.assertEqual(detect_forbidden_groups(malicious), ["impostos.icms", "tipo_debito"])
        with patch("apps.finance.services.fiscal_credit_product_preview._build_product_payload", return_value=(malicious, self.basis.ibs_cbs_snapshot)):
            with self.assertRaisesMessage(ValidationError, "grupos proibidos"):
                self.create_preview()

    def test_approved_preview_payload_is_immutable(self) -> None:
        preview = approve_credit_product_preview(preview=self.create_preview(), approved_by=self.user)
        preview.product_total_amount = Decimal("8.00")
        preview.product_payload["total"] = "8.00"
        with self.assertRaisesMessage(ValidationError, "imutaveis"):
            preview.save()

    def test_disabled_feature_flag_blocks_preview_and_creates_no_emission(self) -> None:
        self.company.credit_debit_basis_enabled = False
        self.company.save(update_fields=["credit_debit_basis_enabled"])
        with self.assertRaisesMessage(ValidationError, "desabilitada"):
            self.create_preview()
        self.assertFalse(FiscalEmissionAttempt.objects.exists())
        self.assertFalse(FiscalDocument.objects.filter(purpose=FiscalDocumentPurpose.CREDIT).exists())

    def test_cross_workshop_is_blocked(self) -> None:
        other_user, other_workshop = _scope(52)
        WebmaniaCompany.objects.create(workshop=other_workshop, credit_debit_basis_enabled=True)
        with self.assertRaises(FiscalReferencedBasis.DoesNotExist):
            self.create_preview(workshop=other_workshop, created_by=other_user)

    def test_create_view_requires_specific_permission_before_service(self) -> None:
        request = RequestFactory().post("/", data={})
        request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
            patch("apps.finance.views.fiscal_credit_product_preview.create_credit_product_preview") as service_mock,
        ):
            with self.assertRaises(PermissionDenied):
                FiscalCreditProductPreviewCreateView.as_view()(request)
        service_mock.assert_not_called()

    def test_approve_view_requires_specific_permission_before_service(self) -> None:
        preview = self.create_preview()
        request = RequestFactory().post("/")
        request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
            patch("apps.finance.views.fiscal_credit_product_preview.approve_credit_product_preview") as service_mock,
        ):
            with self.assertRaises(PermissionDenied):
                FiscalCreditProductPreviewApproveView.as_view()(request, pk=preview.pk)
        service_mock.assert_not_called()

    def test_payload_view_requires_permission_sanitizes_and_scopes_workshop(self) -> None:
        preview = self.create_preview()
        preview.preview_payload["consumer_secret"] = "secret"
        preview.save(update_fields=["preview_payload", "atualizado_em"])
        request = RequestFactory().get("/")
        request.user = self.user
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=False),
        ):
            with self.assertRaises(PermissionDenied):
                FiscalCreditProductPreviewPayloadView.as_view()(request, pk=preview.pk)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=self.workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            response = FiscalCreditProductPreviewPayloadView.as_view()(request, pk=preview.pk)
        self.assertNotIn('"consumer_secret": "secret"', response.content.decode())
        self.assertIn("[REDACTED]", response.content.decode())
        _other_user, other_workshop = _scope(53)
        with (
            patch("apps.workshops.mixin.get_active_workshop_or_404", return_value=other_workshop),
            patch("apps.workshops.mixin.has_workshop_perm", return_value=True),
        ):
            with self.assertRaises(Http404):
                FiscalCreditProductPreviewPayloadView.as_view()(request, pk=preview.pk)
