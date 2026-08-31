from __future__ import annotations

from django.test import SimpleTestCase
from django.utils import timezone

from apps.workorder.models import WORKORDER_STATUS_BADGE_CLASSES, WorkOrder, WorkOrderStatus


class WorkOrderStatusBadgeTests(SimpleTestCase):
    def test_all_statuses_have_styled_badge_classes(self) -> None:
        for status in WorkOrderStatus:
            workorder = WorkOrder(status=status.value)
            badge = workorder.workorder_status_badge
            self.assertEqual(badge["text"], status.label)
            self.assertIn("min-w-sm", badge["class"])
            self.assertNotEqual(badge["class"], "badge-ghost")

    def test_waiting_statuses_use_expected_palette(self) -> None:
        self.assertIn("badge-info", WORKORDER_STATUS_BADGE_CLASSES[WorkOrderStatus.WAITING_COLLABORATOR])
        self.assertIn("badge-warning", WORKORDER_STATUS_BADGE_CLASSES[WorkOrderStatus.WAITING_DELIVERY])

    def test_reopened_delivered_workorder_uses_distinct_badge(self) -> None:
        workorder = WorkOrder(
            status=WorkOrderStatus.WAITING_DELIVERY,
            delivered_at=timezone.now(),
            reopen_reason="Corrigir item da O.S.",
        )

        self.assertEqual(workorder.workorder_status_badge["text"], "Veículo entregue/O.S. Reaberta")
        self.assertIn("badge-reopened-after-delivery", workorder.workorder_status_badge["class"])

    def test_open_workorder_without_previous_delivery_keeps_its_regular_badge(self) -> None:
        workorder = WorkOrder(status=WorkOrderStatus.WAITING_DELIVERY, reopen_reason="Corrigir item da O.S.")

        self.assertEqual(workorder.workorder_status_badge["text"], WorkOrderStatus.WAITING_DELIVERY.label)
