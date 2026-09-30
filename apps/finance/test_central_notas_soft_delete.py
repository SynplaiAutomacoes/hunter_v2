from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase, TestCase
from djmoney.money import Money

from apps.budget.models import BudgetType
from apps.collaborators.test_commissions import create_workshop, create_workorder
from apps.finance.forms.nfe import NfeRequestStep3Form
from apps.finance.models.finance import NfeItem, NfeRequest, NfeRequestStatus, NfseRequest, NfseRequestStatus
from apps.finance.services.emission_line_overrides import (
    apply_line_overrides_to_workorder,
    serialize_item_override_from_cleaned_data,
    upsert_item_override,
)
from apps.finance.services.fiscal_request_soft_delete import (
    FiscalRequestSoftDeleteError,
    is_nfe_request_soft_deletable,
    is_nfse_request_soft_deletable,
    soft_delete_nfe_request,
    soft_delete_nfse_request,
)
from apps.finance.services.workorder_emission import get_workorder_emission_ui_state
from apps.workorder.models import WorkOrder, WorkOrderItem, WorkOrderStatus


def _money(amount: str) -> Money:
    return Money(amount, "BRL")


class FiscalRequestSoftDeleteEligibilityTests(SimpleTestCase):
    def test_nfe_pre_emit_without_reservation_is_soft_deletable(self) -> None:
        nfe_request = SimpleNamespace(
            pk=1,
            status=NfeRequestStatus.CHECKING_PRODUCTS,
            reserved_number=None,
            soft_deleted_at=None,
        )
        with patch("apps.finance.services.fiscal_request_soft_delete.NfeItem.objects.filter") as filter_mock:
            filter_mock.return_value.exists.return_value = False
            self.assertTrue(is_nfe_request_soft_deletable(nfe_request=nfe_request))

    def test_nfe_with_reserved_number_is_not_soft_deletable(self) -> None:
        nfe_request = SimpleNamespace(
            pk=1,
            status=NfeRequestStatus.CHECKING_PRODUCTS,
            reserved_number=123,
            soft_deleted_at=None,
        )
        with patch("apps.finance.services.fiscal_request_soft_delete.NfeItem.objects.filter") as filter_mock:
            filter_mock.return_value.exists.return_value = False
            self.assertFalse(is_nfe_request_soft_deletable(nfe_request=nfe_request))

    def test_nfe_processing_is_not_soft_deletable(self) -> None:
        nfe_request = SimpleNamespace(
            pk=1,
            status=NfeRequestStatus.PROCESSING,
            reserved_number=None,
            soft_deleted_at=None,
        )
        with patch("apps.finance.services.fiscal_request_soft_delete.NfeItem.objects.filter") as filter_mock:
            filter_mock.return_value.exists.return_value = False
            self.assertFalse(is_nfe_request_soft_deletable(nfe_request=nfe_request))

    def test_nfe_with_remote_item_is_not_soft_deletable(self) -> None:
        nfe_request = SimpleNamespace(
            pk=1,
            status=NfeRequestStatus.CHECKING_PRODUCTS,
            reserved_number=None,
            soft_deleted_at=None,
        )
        with patch("apps.finance.services.fiscal_request_soft_delete.NfeItem.objects.filter") as filter_mock:
            filter_mock.return_value.exists.return_value = True
            self.assertFalse(is_nfe_request_soft_deletable(nfe_request=nfe_request))

    def test_nfse_checking_services_is_soft_deletable(self) -> None:
        nfse_request = SimpleNamespace(
            pk=2,
            status=NfseRequestStatus.CHECKING_SERVICES,
            reserved_rps_number=None,
            soft_deleted_at=None,
        )
        with patch("apps.finance.services.fiscal_request_soft_delete.NfseItem.objects.filter") as filter_mock:
            filter_mock.return_value.exists.return_value = False
            self.assertTrue(is_nfse_request_soft_deletable(nfse_request=nfse_request))


class EmissionLineOverridesUnitTests(SimpleTestCase):
    def test_apply_item_override_mutates_in_memory_only(self) -> None:
        item = SimpleNamespace(
            pk=10,
            description="Original",
            quantity=1,
            product_selling_price=_money("10.00"),
            product_cost_price=_money("5.00"),
            shipping=_money("0.00"),
            service_selling_price=_money("0.00"),
            service_cost_price=_money("0.00"),
            duration=None,
            is_customer_supplied=False,
            item_benefit_type="sale",
            kit_id=None,
        )
        workorder = SimpleNamespace(_iter_items=lambda: [item])
        overrides = upsert_item_override(
            line_overrides={},
            item_id=10,
            override=serialize_item_override_from_cleaned_data(
                {
                    "description": "Nota only",
                    "quantity": 3,
                    "product_selling_price": _money("20.00"),
                    "product_cost_price": _money("5.00"),
                    "shipping": _money("0.00"),
                    "is_customer_supplied": False,
                    "item_benefit_type": "sale",
                }
            ),
        )

        apply_line_overrides_to_workorder(workorder=workorder, line_overrides=overrides)

        self.assertEqual(item.description, "Nota only")
        self.assertEqual(item.quantity, 3)
        self.assertEqual(item.product_selling_price, _money("20.00"))


class NfeStep3DiscountOverrideFormTests(SimpleTestCase):
    def test_step3_form_exposes_discount_override_field(self) -> None:
        self.assertIn("discount_value_override", NfeRequestStep3Form.Meta.fields)


class FiscalRequestSoftDeletePersistenceTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=401)
        self.workorder = create_workorder(workshop=self.workshop, budget_type=BudgetType.SALE, status=WorkOrderStatus.APPROVED)

    @patch("apps.finance.services.workorder_emission.build_slider_allocation_for_workorder")
    def test_soft_delete_hides_request_and_allows_new_emission_ui(self, allocation_mock) -> None:
        allocation_mock.return_value = SimpleNamespace(products_target=Decimal("100.00"), services_target=Decimal("50.00"))
        nfe_request = NfeRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            status=NfeRequestStatus.CHECKING_PRODUCTS,
        )
        soft_delete_nfe_request(nfe_request=nfe_request)
        nfe_request.refresh_from_db()
        self.assertIsNotNone(nfe_request.soft_deleted_at)

        ui_state = get_workorder_emission_ui_state(workorder=self.workorder)
        self.assertIsNotNone(ui_state)
        assert ui_state is not None
        self.assertFalse(ui_state.has_nfe)
        self.assertEqual(ui_state.mode, "emit")

    def test_soft_deleted_request_keeps_workorder_in_emission_dropdown(self) -> None:
        from django.db.models import Exists, OuterRef

        nfe_request = NfeRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            status=NfeRequestStatus.CHECKING_PRODUCTS,
        )
        nfse_request = NfseRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            status=NfseRequestStatus.CHECKING_SERVICES,
        )
        soft_delete_nfe_request(nfe_request=nfe_request)
        soft_delete_nfse_request(nfse_request=nfse_request)

        nfe_exists = NfeRequest.objects.filter(workorder=OuterRef("pk"), soft_deleted_at__isnull=True)
        nfse_exists = NfseRequest.objects.filter(workorder=OuterRef("pk"), soft_deleted_at__isnull=True)
        queryset = (
            WorkOrder.objects.filter(workshop=self.workshop, status=WorkOrderStatus.APPROVED)
            .annotate(has_nfe=Exists(nfe_exists), has_nfse=Exists(nfse_exists))
            .exclude(has_nfe=True, has_nfse=True)
        )
        self.assertIn(self.workorder, queryset)

    def test_soft_delete_rejects_request_with_remote_item(self) -> None:
        nfe_request = NfeRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            status=NfeRequestStatus.CHECKING_PRODUCTS,
        )
        NfeItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            request=nfe_request,
            uuid=uuid4(),
        )
        with self.assertRaises(FiscalRequestSoftDeleteError):
            soft_delete_nfe_request(nfe_request=nfe_request)

    def test_soft_delete_wizard_drafts_removes_pre_emit_requests(self) -> None:
        from apps.finance.services.fiscal_request_soft_delete import soft_delete_wizard_draft_requests

        nfe_request = NfeRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            status=NfeRequestStatus.CHECKING_PRODUCTS,
        )
        nfse_request = NfseRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            status=NfseRequestStatus.CHECKING_SERVICES,
        )
        processing = NfeRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            status=NfeRequestStatus.PROCESSING,
        )

        deleted = soft_delete_wizard_draft_requests(
            workshop=self.workshop,
            state={
                "nfe_request_id": nfe_request.pk,
                "nfse_request_id": nfse_request.pk,
            },
        )
        # processing id not in state — leave alone; also verify processing would be skipped
        soft_delete_wizard_draft_requests(
            workshop=self.workshop,
            state={"nfe_request_id": processing.pk},
        )

        nfe_request.refresh_from_db()
        nfse_request.refresh_from_db()
        processing.refresh_from_db()
        self.assertEqual(len(deleted), 2)
        self.assertIsNotNone(nfe_request.soft_deleted_at)
        self.assertIsNotNone(nfse_request.soft_deleted_at)
        self.assertIsNone(processing.soft_deleted_at)


class EmissionWizardResetSoftDeletesDraftsTests(TestCase):
    def setUp(self) -> None:
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.backends.db import SessionStore
        from django.test import RequestFactory

        from apps.finance.views.emission import EmissionRequestCreateView

        self.factory = RequestFactory()
        self.workshop = create_workshop(suffix=403)
        self.workorder = create_workorder(workshop=self.workshop, budget_type=BudgetType.SALE, status=WorkOrderStatus.APPROVED)
        self.EmissionRequestCreateView = EmissionRequestCreateView
        self.SessionStore = SessionStore
        self.FallbackStorage = FallbackStorage

    def test_reset_soft_deletes_session_drafts_and_frees_workorder(self) -> None:
        from django.db.models import Exists, OuterRef

        nfe_request = NfeRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            status=NfeRequestStatus.CHECKING_PRODUCTS,
        )
        nfse_request = NfseRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            status=NfseRequestStatus.CHECKING_SERVICES,
        )

        request = self.factory.get("/finance/emissao/normal/?reset=1")
        request.user = None
        request.session = self.SessionStore()
        setattr(request, "_messages", self.FallbackStorage(request))

        view = self.EmissionRequestCreateView()
        view.request = request
        view.workshop = self.workshop
        request.session[view._session_key()] = {
            "current_step": 5,
            "max_reached_step": 5,
            "workorder_id": self.workorder.pk,
            "nfe_request_id": nfe_request.pk,
            "nfse_request_id": nfse_request.pk,
            "nfe_done": False,
            "nfse_done": False,
        }

        response = view.get(request)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(view._session_key(), request.session)

        nfe_request.refresh_from_db()
        nfse_request.refresh_from_db()
        self.assertIsNotNone(nfe_request.soft_deleted_at)
        self.assertIsNotNone(nfse_request.soft_deleted_at)

        nfe_exists = NfeRequest.objects.filter(workorder=OuterRef("pk"), soft_deleted_at__isnull=True)
        nfse_exists = NfseRequest.objects.filter(workorder=OuterRef("pk"), soft_deleted_at__isnull=True)
        queryset = (
            WorkOrder.objects.filter(workshop=self.workshop, status=WorkOrderStatus.APPROVED)
            .annotate(has_nfe=Exists(nfe_exists), has_nfse=Exists(nfse_exists))
            .exclude(has_nfe=True, has_nfse=True)
        )
        self.assertIn(self.workorder, queryset)


class EmissionItemOverrideIsolationTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=402)
        self.workorder = create_workorder(workshop=self.workshop, budget_type=BudgetType.SALE, status=WorkOrderStatus.APPROVED)
        self.item = WorkOrderItem.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            description="Peca original",
            quantity=1,
            product_selling_price=_money("10.00"),
            product_cost_price=_money("4.00"),
        )

    def test_line_override_does_not_persist_on_workorder_item(self) -> None:
        original_description = self.item.description
        original_qty = self.item.quantity
        overrides = upsert_item_override(
            line_overrides={},
            item_id=self.item.pk,
            override=serialize_item_override_from_cleaned_data(
                {
                    "description": "Peca na nota",
                    "quantity": 5,
                    "product_selling_price": _money("99.00"),
                    "product_cost_price": _money("4.00"),
                    "shipping": _money("0.00"),
                    "is_customer_supplied": False,
                    "item_benefit_type": self.item.item_benefit_type,
                }
            ),
        )
        nfe_request = NfeRequest.objects.create(
            workshop=self.workshop,
            workorder=self.workorder,
            status=NfeRequestStatus.CHECKING_PRODUCTS,
            line_overrides=overrides,
        )

        apply_line_overrides_to_workorder(workorder=self.workorder, line_overrides=nfe_request.line_overrides)
        in_memory_item = next(item for item in self.workorder._iter_items() if item.pk == self.item.pk)
        self.assertEqual(in_memory_item.description, "Peca na nota")
        self.assertEqual(in_memory_item.quantity, 5)

        self.item.refresh_from_db()
        self.assertEqual(self.item.description, original_description)
        self.assertEqual(self.item.quantity, original_qty)
