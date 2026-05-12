from __future__ import annotations

import json

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.budget.models import BudgetItem
from apps.budget.models import Budget, BudgetStatus, SignatureStatus
from apps.catalog.models.groups import CatalogGroup
from apps.catalog.models.products import Product
from apps.core.documents.webhook import extract_supersign_envelope_id, extract_supersign_event
from apps.workorder.models import WorkOrder, WorkOrderSignatureStatus, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Webhook {suffix}",
        cnpj=f"22.333.444/0001-{suffix:02d}",
        phone="+5511977777777",
        address="Rua Webhook, 123",
    )


def create_budget(*, workshop: Workshop) -> Budget:
    budget = Budget(workshop=workshop, entry_date=timezone.now().date())
    budget.save()
    return budget


class SuperSignWebhookParsingTests(SimpleTestCase):
    def test_extract_supersign_event_normalizes_aliases(self) -> None:
        payload = {"eventType": "document-completed"}

        self.assertEqual(extract_supersign_event(payload), "ENVELOPE_COMPLETED")

    def test_extract_supersign_envelope_id_reads_nested_envelope(self) -> None:
        payload = {"data": {"envelope": {"id": "env-123"}}}

        self.assertEqual(extract_supersign_envelope_id(payload), "env-123")


@override_settings(SUPERSIGN_API_KEY="secret", SUPERSIGN_ACCOUNT_ID="acc-1")
class SuperSignWebhookViewTests(TestCase):
    def test_ping_route_returns_webhook_online(self) -> None:
        response = self.client.get(reverse("budget:supersign_webhook_ping"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "message": "webhook online"})

    def test_post_rejects_invalid_authorization(self) -> None:
        response = self.client.post(
            reverse("budget:supersign_webhook"),
            data=json.dumps({"event": "ENVELOPE_COMPLETED", "envelopeId": "env-123"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer wrong",
            HTTP_X_ACCOUNT_ID="acc-1",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "invalid_authorization"})

    def test_post_approves_matching_budget_and_workorder(self) -> None:
        workshop = create_workshop(suffix=91)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)

        budget.mark_signature_sent("env-123")
        workorder.mark_signature_sent("env-123")

        response = self.client.post(
            reverse("budget:supersign_webhook"),
            data=json.dumps({"event": "ENVELOPE_COMPLETED", "envelopeId": "env-123"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer secret",
            HTTP_X_ACCOUNT_ID="acc-1",
        )

        budget.refresh_from_db()
        workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(budget.status, BudgetStatus.APPROVED)
        self.assertEqual(budget.signature_request_status, SignatureStatus.APPROVED)
        self.assertEqual(workorder.status, WorkOrderStatus.APPROVED)
        self.assertEqual(workorder.signature_request_status, WorkOrderSignatureStatus.APPROVED)

    def test_post_ignores_non_completed_events(self) -> None:
        workshop = create_workshop(suffix=92)
        budget = create_budget(workshop=workshop)
        budget.mark_signature_sent("env-456")

        response = self.client.post(
            reverse("budget:supersign_webhook"),
            data=json.dumps({"event": "ENVELOPE_VIEWED", "envelopeId": "env-456"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer secret",
            HTTP_X_ACCOUNT_ID="acc-1",
        )

        budget.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(budget.status, BudgetStatus.DRAFT)
        self.assertEqual(budget.signature_request_status, SignatureStatus.SENT)

    def test_post_approves_matching_workorder_without_budget_signature(self) -> None:
        workshop = create_workshop(suffix=93)
        budget = create_budget(workshop=workshop)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.mark_signature_sent("env-789")

        response = self.client.post(
            reverse("budget:supersign_webhook"),
            data=json.dumps({"event": "ENVELOPE_COMPLETED", "envelopeId": "env-789"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer secret",
            HTTP_X_ACCOUNT_ID="acc-1",
        )

        budget.refresh_from_db()
        workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(budget.status, BudgetStatus.DRAFT)
        self.assertEqual(budget.signature_request_status, SignatureStatus.NOT_SENT)
        self.assertEqual(workorder.status, WorkOrderStatus.APPROVED)
        self.assertEqual(workorder.signature_request_status, WorkOrderSignatureStatus.APPROVED)

    def test_post_without_auth_headers_is_accepted_without_warning(self) -> None:
        workshop = create_workshop(suffix=94)
        budget = create_budget(workshop=workshop)
        budget.mark_signature_sent("env-790")

        with self.assertNoLogs("apps.core.documents.webhook", level="WARNING"):
            response = self.client.post(
                reverse("budget:supersign_webhook"),
                data=json.dumps({"event": "ENVELOPE_COMPLETED", "envelopeId": "env-790"}),
                content_type="application/json",
            )

        budget.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(budget.status, BudgetStatus.APPROVED)
        self.assertEqual(budget.signature_request_status, SignatureStatus.APPROVED)

    def test_post_marks_signature_approved_without_delivering_unpaid_workorder(self) -> None:
        workshop = create_workshop(suffix=95)
        budget = create_budget(workshop=workshop)
        product = Product.objects.create(
            workshop=workshop,
            code="P-WEBHOOK-95",
            unit=Product.Unit.UND,
            name="Produto Webhook",
            ncm="87089990",
            group=CatalogGroup.objects.create(workshop=workshop, name="Grupo Webhook"),
            cost_price="10.00",
            selling_price="80.00",
        )
        BudgetItem.objects.create(workshop=workshop, budget=budget, product=product, quantity=1)
        workorder = WorkOrder.objects.create(workshop=workshop, budget=budget)
        workorder.sync_from_budget()
        workorder.mark_signature_sent("env-791")

        response = self.client.post(
            reverse("budget:supersign_webhook"),
            data=json.dumps({"event": "ENVELOPE_COMPLETED", "envelopeId": "env-791"}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer secret",
            HTTP_X_ACCOUNT_ID="acc-1",
        )

        workorder.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(workorder.signature_request_status, WorkOrderSignatureStatus.APPROVED)
        self.assertEqual(workorder.status, WorkOrderStatus.DRAFT)
        self.assertIsNone(workorder.delivered_at)
