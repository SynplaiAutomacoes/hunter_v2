from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.budget.models import SignatureStatus
from apps.core.infrastructure.services.supersign import process_supersign_webhook_payload


class BudgetWebhookTests(SimpleTestCase):
    def test_webhook_marks_signature_approved_when_budget_already_approved(self) -> None:
        budget = SimpleNamespace(
            pk=1,
            signature_request_status=SignatureStatus.APPROVED,
            approve=lambda: False,
            mark_signature_approved=Mock(),
        )

        with patch("apps.budget.models.Budget.objects") as budget_objects:
            with patch("apps.workorder.models.WorkOrder.objects") as workorder_objects:
                budget_objects.filter.return_value.first.return_value = budget
                workorder_objects.filter.return_value.first.return_value = None

                response = process_supersign_webhook_payload(
                    payload={"event": "ENVELOPE_COMPLETED", "envelopeId": "env-1"},
                )

        self.assertEqual(response.status_code, 200)
        budget.mark_signature_approved.assert_called_once()
