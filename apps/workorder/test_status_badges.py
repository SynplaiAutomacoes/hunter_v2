from __future__ import annotations

from django.test import SimpleTestCase

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
