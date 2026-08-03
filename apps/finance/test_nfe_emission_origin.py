from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Account
from apps.budget.models import Budget
from apps.core.infrastructure.services.webmania.nfe_emission import build_nfe_payload
from apps.customer.models import Customer
from apps.finance.models import FiscalEmissionDocumentKind, NfeEmissionOrigin, NfeRequest
from apps.finance.services.fiscal_attempts import begin_emission_attempt
from apps.finance.views.emission import EmissionRequestCreateView
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


class NfeEmissionOriginModelTests(TestCase):
    def setUp(self) -> None:
        account = Account.objects.create(name="Conta origem NF-e")
        self.workshop = Workshop.objects.create(
            account=account,
            name="Oficina origem NF-e",
            cnpj="12.345.678/0001-90",
            phone="+5511999999999",
            address="Rua Origem, 10",
        )
        budget = Budget.objects.create(workshop=self.workshop, entry_date=timezone.localdate())
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=budget, status=WorkOrderStatus.APPROVED)
        self.recipient = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Manual",
            cpf_or_cnpj="52998224725",
            email="manual@example.com",
        )

    def test_existing_work_order_flow_persists_explicit_work_order_origin(self) -> None:
        state: dict[str, object] = {
            "nfe_request_id": None,
            "nfe_config": {
                "tax_class": "REFNFE",
                "additional_information": "",
                "freight_mode": 9,
                "transport_snapshot": {},
            },
            "discount_type_override": "",
        }
        view = EmissionRequestCreateView()
        view.workshop = self.workshop
        view._write_state = Mock()  # type: ignore[method-assign]

        nfe_request = view._get_or_create_nfe_request(state=state, workorder=self.workorder)

        self.assertEqual(nfe_request.emission_origin, NfeEmissionOrigin.WORK_ORDER)
        self.assertEqual(nfe_request.workorder, self.workorder)

    def test_manual_origin_can_be_persisted_without_work_order(self) -> None:
        nfe_request = NfeRequest.objects.create(
            workshop=self.workshop,
            emission_origin=NfeEmissionOrigin.MANUAL,
            manual_recipient=self.recipient,
        )

        nfe_request.refresh_from_db()
        self.assertEqual(nfe_request.emission_origin, NfeEmissionOrigin.MANUAL)
        self.assertIsNone(nfe_request.workorder)
        self.assertEqual(nfe_request.customer_name, self.recipient.name)

    def test_database_constraint_rejects_origin_and_work_order_mismatch(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            NfeRequest.objects.create(
                workshop=self.workshop,
                workorder=self.workorder,
                emission_origin=NfeEmissionOrigin.MANUAL,
                manual_recipient=self.recipient,
            )

        with self.assertRaises(IntegrityError), transaction.atomic():
            NfeRequest.objects.create(
                workshop=self.workshop,
                emission_origin=NfeEmissionOrigin.WORK_ORDER,
            )

    def test_fiscal_emission_attempt_keeps_using_the_same_nfe_request_identity(self) -> None:
        nfe_request = NfeRequest.objects.create(workshop=self.workshop, workorder=self.workorder)

        attempt = begin_emission_attempt(
            workshop=self.workshop,
            document_kind=FiscalEmissionDocumentKind.NFE,
            request_model="NfeRequest",
            request_id=nfe_request.pk,
            request_payload={"pedido": {"total": "100.00"}},
        )

        self.assertEqual(attempt.request_id, nfe_request.pk)
        self.assertEqual(attempt.request_model, "NfeRequest")
        self.assertEqual(attempt.document_kind, FiscalEmissionDocumentKind.NFE)


@override_settings(WEBMANIA_NFE_NATUREZA_OPERACAO="Venda de mercadoria", WEBMANIA_AMBIENT="2")
class NfeEmissionOriginPayloadCompatibilityTests(SimpleTestCase):
    @staticmethod
    def _nfe_request(*, include_origin: bool) -> SimpleNamespace:
        payments = Mock()
        payments.order_by.return_value.first.return_value = None
        values = {
            "pk": 11,
            "workshop": SimpleNamespace(pk=33),
            "workorder": SimpleNamespace(pk=22, payments=payments, discount_type="products"),
            "tax_class": "REF-NFE",
            "additional_information": "",
            "freight_mode": 9,
            "transport_snapshot": {},
        }
        if include_origin:
            values["emission_origin"] = NfeEmissionOrigin.WORK_ORDER
        return SimpleNamespace(**values)

    @staticmethod
    def _build_payload(nfe_request: SimpleNamespace) -> dict[str, object]:
        allocation = SimpleNamespace(products_target=Decimal("100.00"), services_target=Decimal("0.00"), slider=0)
        with (
            patch(
                "apps.core.infrastructure.services.webmania.nfe_emission._build_nfe_products_payload",
                return_value=([{"codigo": "P1"}], Decimal("100.00"), allocation, Decimal("0.00")),
            ),
            patch("apps.core.infrastructure.services.webmania.nfe_emission._build_customer_payload", return_value={"cpf": "52998224725"}),
            patch("apps.core.infrastructure.services.webmania.nfe_emission.build_webmania_webhook_url", return_value="https://example.test/webhook"),
        ):
            return build_nfe_payload(nfe_request=nfe_request)

    def test_work_order_origin_does_not_change_existing_webmania_payload(self) -> None:
        payload_before_origin_support = self._build_payload(self._nfe_request(include_origin=False))
        payload_with_work_order_origin = self._build_payload(self._nfe_request(include_origin=True))

        self.assertEqual(payload_with_work_order_origin, payload_before_origin_support)
        self.assertNotIn("emission_origin", payload_with_work_order_origin)
