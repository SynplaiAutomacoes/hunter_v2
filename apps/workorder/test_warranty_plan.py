from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.budget.models import Budget
from apps.core.infrastructure.services.signature_webhook import process_signature_webhook_payload
from apps.customer.models import Customer, Vehicle
from apps.customer.views import _build_customer_workorder_history_entry
from apps.workorder.forms import WorkOrderCustomerApprovalForm
from apps.workorder.models import WorkOrder, WorkOrderStatus, WorkOrderWarrantyPlan
from apps.workshops.models.workshops import Workshop


def _create_workshop(*, suffix: int) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Garantia {suffix}",
        cnpj=f"11.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Garantia, 100",
    )


def _create_workorder(*, workshop: Workshop, suffix: int) -> WorkOrder:
    customer = Customer.objects.create(
        workshop=workshop,
        name=f"Cliente Garantia {suffix}",
        cpf_or_cnpj=f"1234567890{suffix:02d}",
        email=f"garantia{suffix}@example.com",
        is_active=True,
    )
    vehicle = Vehicle.objects.create(
        workshop=workshop,
        customer=customer,
        plate=f"GAR{suffix:04d}",
        brand="Fiat",
        model="Uno",
        year_fabrication="2020",
        year_model="2020",
    )
    budget = Budget.objects.create(
        workshop=workshop,
        customer=customer,
        vehicle=vehicle,
        entry_date=timezone.localdate(),
        slider=0,
    )
    return WorkOrder.objects.create(workshop=workshop, budget=budget)


class WorkOrderWarrantyPlanModelTests(TestCase):
    def test_complete_delivery_persists_warranty_plan(self) -> None:
        workshop = _create_workshop(suffix=1)
        workorder = _create_workorder(workshop=workshop, suffix=1)

        workorder.complete_delivery(km_final=10_000, warranty_plan=WorkOrderWarrantyPlan.DAYS_90)
        workorder.refresh_from_db()

        self.assertEqual(workorder.warranty_plan, WorkOrderWarrantyPlan.DAYS_90)
        self.assertEqual(workorder.warranty_days, 90)
        self.assertEqual(workorder.warranty_plan_display, "90 dias")

    def test_warranty_status_in_period_and_expired(self) -> None:
        workshop = _create_workshop(suffix=2)
        workorder = _create_workorder(workshop=workshop, suffix=2)
        workorder.warranty_plan = WorkOrderWarrantyPlan.DAYS_30
        workorder.delivered_at = timezone.now() - timedelta(days=10)
        workorder.save(update_fields=["warranty_plan", "delivered_at"])

        self.assertEqual(workorder.warranty_status_label, "Em garantia")
        self.assertEqual(workorder.warranty_expires_at, timezone.localtime(workorder.delivered_at).date() + timedelta(days=30))

        workorder.delivered_at = timezone.now() - timedelta(days=40)
        workorder.save(update_fields=["delivered_at"])
        self.assertEqual(workorder.warranty_status_label, "Garantia vencida")

    def test_warranty_status_none_plan(self) -> None:
        workshop = _create_workshop(suffix=3)
        workorder = _create_workorder(workshop=workshop, suffix=3)
        workorder.warranty_plan = WorkOrderWarrantyPlan.NONE
        workorder.delivered_at = timezone.now()
        workorder.save(update_fields=["warranty_plan", "delivered_at"])

        self.assertEqual(workorder.warranty_status_label, "Sem garantia")
        self.assertIsNone(workorder.warranty_expires_at)
        self.assertIsNone(workorder.warranty_days)

    def test_warranty_status_without_plan_or_delivery(self) -> None:
        workshop = _create_workshop(suffix=4)
        workorder = _create_workorder(workshop=workshop, suffix=4)

        self.assertIsNone(workorder.warranty_status_label)
        self.assertIsNone(workorder.warranty_expires_at)

        workorder.warranty_plan = WorkOrderWarrantyPlan.DAYS_90
        workorder.save(update_fields=["warranty_plan"])
        self.assertIsNone(workorder.warranty_status_label)


class WorkOrderWarrantyPlanFormTests(TestCase):
    def test_form_requires_warranty_plan_on_delivery(self) -> None:
        workshop = _create_workshop(suffix=5)
        workorder = _create_workorder(workshop=workshop, suffix=5)

        form = WorkOrderCustomerApprovalForm(
            data={"km_final": "12000", "warranty_plan": ""},
            workorder=workorder,
            require_unsigned_delivery_reason=False,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("warranty_plan", form.errors)

    def test_form_accepts_warranty_plan(self) -> None:
        workshop = _create_workshop(suffix=6)
        workorder = _create_workorder(workshop=workshop, suffix=6)

        form = WorkOrderCustomerApprovalForm(
            data={"km_final": "12000", "warranty_plan": WorkOrderWarrantyPlan.DAYS_180},
            workorder=workorder,
            require_unsigned_delivery_reason=False,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["warranty_plan"], WorkOrderWarrantyPlan.DAYS_180)

    def test_km_final_update_skips_warranty_requirement(self) -> None:
        workshop = _create_workshop(suffix=7)
        workorder = _create_workorder(workshop=workshop, suffix=7)

        form = WorkOrderCustomerApprovalForm(
            data={"km_final": "15000"},
            workorder=workorder,
            require_unsigned_delivery_reason=False,
            require_warranty_plan=False,
        )
        self.assertTrue(form.is_valid(), form.errors)


class WorkOrderWarrantyHistoryEntryTests(TestCase):
    def test_history_entry_includes_delivery_and_warranty(self) -> None:
        workshop = _create_workshop(suffix=8)
        workorder = _create_workorder(workshop=workshop, suffix=8)
        workorder.warranty_plan = WorkOrderWarrantyPlan.DAYS_90
        workorder.delivered_at = timezone.now() - timedelta(days=5)
        workorder.status = WorkOrderStatus.APPROVED
        workorder.save(update_fields=["warranty_plan", "delivered_at", "status"])

        entry = _build_customer_workorder_history_entry(workorder)
        self.assertEqual(entry["delivered_at"], workorder.delivered_at)
        self.assertEqual(entry["warranty_status_label"], "Em garantia")


class SignatureWebhookWarrantyGateTests(SimpleTestCase):
    @patch("apps.messaging.application.services.satisfaction_survey.schedule_satisfaction_survey_for_workorder")
    @patch("apps.core.infrastructure.services.signature_webhook.approve_workorder_with_stock")
    @patch("apps.core.infrastructure.services.signature_webhook.sync_workorder_financial_movement")
    def test_webhook_finalizes_with_default_warranty_when_paid(
        self,
        sync_finance_mock: Mock,
        approve_mock: Mock,
        schedule_survey_mock: Mock,
    ) -> None:
        workorder = SimpleNamespace(
            pk=99,
            is_fully_paid=True,
            budget_type="sale",
            status=WorkOrderStatus.DRAFT,
            warranty_plan=None,
            mark_signature_approved=Mock(),
            refresh_from_db=Mock(),
        )

        response = process_signature_webhook_payload(
            payload={"event": "ENVELOPE_COMPLETED", "envelopeId": "env-warranty-1"},
            workorder=workorder,
        )

        self.assertEqual(response.status_code, 200)
        approve_mock.assert_called_once()
        sync_finance_mock.assert_called_once()
        schedule_survey_mock.assert_called_once()
        # mark_signature_approved não deve ser chamado quando workflow pode ser finalizado
        assert not workorder.mark_signature_approved.called
        # warranty_plan deve ter sido defaultado para DAYS_90
        assert workorder.warranty_plan == WorkOrderWarrantyPlan.DAYS_90

    @patch("apps.messaging.application.services.satisfaction_survey.schedule_satisfaction_survey_for_workorder")
    @patch("apps.core.infrastructure.services.signature_webhook.approve_workorder_with_stock")
    @patch("apps.core.infrastructure.services.signature_webhook.sync_workorder_financial_movement")
    def test_webhook_finalizes_when_warranty_plan_present(
        self,
        sync_finance_mock: Mock,
        approve_mock: Mock,
        schedule_survey_mock: Mock,
    ) -> None:
        workorder = SimpleNamespace(
            pk=100,
            is_fully_paid=True,
            budget_type="sale",
            status=WorkOrderStatus.DRAFT,
            warranty_plan=WorkOrderWarrantyPlan.DAYS_90,
            mark_signature_approved=Mock(),
            refresh_from_db=Mock(),
        )

        response = process_signature_webhook_payload(
            payload={"event": "ENVELOPE_COMPLETED", "envelopeId": "env-warranty-2"},
            workorder=workorder,
        )

        self.assertEqual(response.status_code, 200)
        approve_mock.assert_called_once()
        sync_finance_mock.assert_called_once()
        schedule_survey_mock.assert_called_once_with(workorder)
        workorder.mark_signature_approved.assert_not_called()
