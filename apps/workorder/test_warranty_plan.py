from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account
from apps.budget.models import Budget
from apps.collaborators.models import WorkshopMember
from apps.collaborators.test_commissions import create_collaborator
from apps.core.infrastructure.services.signature_webhook import process_signature_webhook_payload
from apps.customer.models import Customer, Vehicle
from apps.customer.views import _build_customer_workorder_history_entry
from apps.iam.utils import get_or_create_director_role
from apps.workorder.forms import WorkOrderCustomerApprovalForm
from apps.workorder.models import WorkOrder, WorkOrderCourtesyReasonType, WorkOrderSignatureStatus, WorkOrderStatus, WorkOrderWarrantyPlan
from apps.workshops.models.workshops import Workshop


User = get_user_model()


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

    def test_draft_form_allows_empty_km_final(self) -> None:
        workshop = _create_workshop(suffix=10)
        workorder = _create_workorder(workshop=workshop, suffix=10)

        form = WorkOrderCustomerApprovalForm(
            data={"km_final": "", "warranty_plan": WorkOrderWarrantyPlan.DAYS_90},
            workorder=workorder,
            require_unsigned_delivery_reason=False,
            require_warranty_plan=False,
            require_km_final=False,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["km_final"])
        self.assertEqual(form.cleaned_data["warranty_plan"], WorkOrderWarrantyPlan.DAYS_90)

    def test_save_delivery_draft_persists_warranty_without_completing(self) -> None:
        workshop = _create_workshop(suffix=11)
        workorder = _create_workorder(workshop=workshop, suffix=11)

        workorder.save_delivery_draft(
            cleaned_data={"warranty_plan": WorkOrderWarrantyPlan.DAYS_30, "km_final": None},
            posted_fields={"warranty_plan", "km_final"},
        )
        workorder.refresh_from_db()

        self.assertEqual(workorder.warranty_plan, WorkOrderWarrantyPlan.DAYS_30)
        self.assertIsNone(workorder.km_final)
        self.assertNotEqual(workorder.status, WorkOrderStatus.APPROVED)
        self.assertIsNone(workorder.delivered_at)

    def test_courtesy_reason_fields_render_for_warranty_workorder(self) -> None:
        workshop = _create_workshop(suffix=13)
        workorder = _create_workorder(workshop=workshop, suffix=13)
        workorder.budget.budget_type = "warranty"
        workorder.budget.save(update_fields=["budget_type"])
        workorder.budget_type = "warranty"
        workorder.save(update_fields=["budget_type"])

        form = WorkOrderCustomerApprovalForm(
            workorder=workorder,
            require_unsigned_delivery_reason=False,
        )
        self.assertTrue(form.is_courtesy_or_warranty)
        self.assertFalse(form.fields["courtesy_reason_type"].disabled)
        self.assertFalse(form.fields["previous_mechanic"].disabled)

    def test_courtesy_reason_fields_disabled_for_sale_workorder(self) -> None:
        workshop = _create_workshop(suffix=14)
        workorder = _create_workorder(workshop=workshop, suffix=14)

        form = WorkOrderCustomerApprovalForm(
            workorder=workorder,
            require_unsigned_delivery_reason=False,
        )
        self.assertFalse(form.is_courtesy_or_warranty)
        self.assertTrue(form.fields["previous_mechanic"].disabled)
        self.assertTrue(form.fields["courtesy_reason_type"].disabled)
        self.assertTrue(form.fields["courtesy_reason_description"].disabled)

    def test_save_delivery_draft_persists_courtesy_fields(self) -> None:
        workshop = _create_workshop(suffix=15)
        workorder = _create_workorder(workshop=workshop, suffix=15)
        workorder.budget_type = "warranty"
        workorder.save(update_fields=["budget_type"])
        mechanic = create_collaborator(workshop=workshop, suffix=15)

        workorder.save_delivery_draft(
            cleaned_data={
                "previous_mechanic": mechanic,
                "courtesy_reason_type": WorkOrderCourtesyReasonType.LABOR_FAILURE,
                "courtesy_reason_description": "Serviço refeito em garantia.",
            },
            posted_fields={"previous_mechanic", "courtesy_reason_type", "courtesy_reason_description"},
        )
        workorder.refresh_from_db()

        self.assertEqual(workorder.previous_mechanic_id, mechanic.pk)
        self.assertEqual(workorder.courtesy_reason_type, WorkOrderCourtesyReasonType.LABOR_FAILURE)
        self.assertEqual(workorder.courtesy_reason_description, "Serviço refeito em garantia.")

    def test_complete_delivery_persists_courtesy_fields(self) -> None:
        workshop = _create_workshop(suffix=16)
        workorder = _create_workorder(workshop=workshop, suffix=16)
        workorder.budget_type = "warranty"
        workorder.save(update_fields=["budget_type"])
        mechanic = create_collaborator(workshop=workshop, suffix=16)

        workorder.complete_delivery(
            km_final=12_000,
            warranty_plan=WorkOrderWarrantyPlan.DAYS_90,
            previous_mechanic_id=mechanic.pk,
            courtesy_reason_type=WorkOrderCourtesyReasonType.PART_DEFECT,
            courtesy_reason_description="Peça com defeito de fábrica.",
            update_courtesy_fields=True,
        )
        workorder.refresh_from_db()

        self.assertEqual(workorder.previous_mechanic_id, mechanic.pk)
        self.assertEqual(workorder.courtesy_reason_type, WorkOrderCourtesyReasonType.PART_DEFECT)
        self.assertEqual(workorder.courtesy_reason_description, "Peça com defeito de fábrica.")


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
            save=Mock(),
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


class WorkOrderDeliveryDraftAutosaveViewTests(TestCase):
    def setUp(self) -> None:
        account = Account.objects.create(name="Conta Draft OS")
        self.user = User.objects.create_user(username="draft-os-user", password="secret", cpf="52998224725")
        self.user.account = account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=account,
            name="Oficina Draft OS",
            cnpj="11.222.333/0001-99",
            phone="+5511999999999",
            address="Rua Draft, 1",
        )
        role = get_or_create_director_role(account=account)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.workorder = _create_workorder(workshop=self.workshop, suffix=12)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()
        self.url = reverse("workorder:update_km_final", kwargs={"pk": self.workorder.pk})

    def test_post_persists_warranty_plan_without_km_or_delivery(self) -> None:
        response = self.client.post(
            self.url,
            data={"warranty_plan": WorkOrderWarrantyPlan.DAYS_90, "km_final": ""},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["km_final"])
        self.assertEqual(payload["warranty_plan"], WorkOrderWarrantyPlan.DAYS_90)
        self.assertFalse(payload["finalized"])

        self.workorder.refresh_from_db()
        self.assertEqual(self.workorder.warranty_plan, WorkOrderWarrantyPlan.DAYS_90)
        self.assertIsNone(self.workorder.km_final)
        self.assertIsNone(self.workorder.delivered_at)
        self.assertEqual(self.workorder.status, WorkOrderStatus.DRAFT)

    @patch("apps.messaging.application.services.satisfaction_survey.schedule_satisfaction_survey_for_workorder")
    @patch("apps.workorder.views.sync_workorder_financial_movement")
    @patch("apps.workorder.views.approve_workorder_with_stock")
    def test_post_finalizes_when_signature_already_approved(
        self,
        approve_mock: Mock,
        sync_finance_mock: Mock,
        schedule_survey_mock: Mock,
    ) -> None:
        def _mark_approved(*, workorder, signature_approved=False, user=None):
            workorder.status = WorkOrderStatus.APPROVED
            workorder.save(update_fields=["status"])

        approve_mock.side_effect = _mark_approved
        self.workorder.budget.budget_type = "warranty"
        self.workorder.budget.save(update_fields=["budget_type"])
        self.workorder.signature_request_status = WorkOrderSignatureStatus.APPROVED
        self.workorder.budget_type = "warranty"
        self.workorder.save(update_fields=["signature_request_status", "budget_type"])

        response = self.client.post(
            self.url,
            data={"warranty_plan": WorkOrderWarrantyPlan.DAYS_90, "km_final": ""},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["finalized"])
        approve_mock.assert_called_once()
        sync_finance_mock.assert_called_once()
        schedule_survey_mock.assert_called_once()

    @patch("apps.messaging.application.services.satisfaction_survey.schedule_satisfaction_survey_for_workorder")
    @patch("apps.workorder.views.sync_workorder_financial_movement")
    @patch("apps.workorder.views.approve_workorder_with_stock")
    def test_post_does_not_finalize_reopened_workorder_on_autosave(
        self,
        approve_mock: Mock,
        sync_finance_mock: Mock,
        schedule_survey_mock: Mock,
    ) -> None:
        self.workorder.budget.budget_type = "warranty"
        self.workorder.budget.save(update_fields=["budget_type"])
        self.workorder.signature_request_status = WorkOrderSignatureStatus.APPROVED
        self.workorder.budget_type = "warranty"
        self.workorder.reopen_reason = "Corrigir item da O.S."
        self.workorder.status = WorkOrderStatus.WAITING_DELIVERY
        self.workorder.save(update_fields=["signature_request_status", "budget_type", "reopen_reason", "status"])

        response = self.client.post(
            self.url,
            data={"warranty_plan": WorkOrderWarrantyPlan.DAYS_90, "km_final": "15000"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["finalized"])
        approve_mock.assert_not_called()
        sync_finance_mock.assert_not_called()
        schedule_survey_mock.assert_not_called()

        self.workorder.refresh_from_db()
        self.assertEqual(self.workorder.status, WorkOrderStatus.WAITING_DELIVERY)
        self.assertEqual(self.workorder.km_final, 15000)
        self.assertEqual(self.workorder.warranty_plan, WorkOrderWarrantyPlan.DAYS_90)
