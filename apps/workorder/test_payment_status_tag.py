from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "workorder" / "partials"


class WorkOrderPaymentStatusTagRemovalTests(SimpleTestCase):
    def test_os_payment_templates_do_not_render_paid_pending_badge(self) -> None:
        payment = (TEMPLATES_DIR / "payment_section.html").read_text(encoding="utf-8")
        resume = (TEMPLATES_DIR / "resume_section.html").read_text(encoding="utf-8")

        self.assertNotIn("status_badge_label", payment)
        self.assertNotIn("status_badge_class", payment)
        self.assertNotIn("status_badge_label", resume)
        self.assertNotIn("status_badge_class", resume)
        self.assertNotIn("payment_status_map", payment)
        self.assertNotIn("payment_rows", payment)
        self.assertNotIn("payment_rows", resume)
