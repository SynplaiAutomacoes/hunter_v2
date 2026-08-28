from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from apps.core.utils import alert_confirm_layout


PAYMENT_SECTION = Path(__file__).resolve().parents[2] / "workorder" / "templates" / "workorder" / "partials" / "payment_section.html"
WORKORDER_DETAIL = Path(__file__).resolve().parents[2] / "workorder" / "templates" / "workorder" / "workorder_detail.html"


class AlertConfirmLayoutTests(SimpleTestCase):
    def test_htmx_confirm_skips_second_prompt_and_binds_once(self) -> None:
        html = str(alert_confirm_layout().html)

        self.assertIn("issueRequest(true)", html)
        self.assertIn("__hunterHtmxConfirmBound", html)
        self.assertIn("item.closest('.hidden')", html)
        self.assertNotIn("evt.detail.issueRequest();", html)

    def test_workorder_payment_delete_uses_htmx_delete_without_form_submit(self) -> None:
        payment = PAYMENT_SECTION.read_text(encoding="utf-8")
        detail = WORKORDER_DETAIL.read_text(encoding="utf-8")

        self.assertIn('type="button"', payment)
        self.assertIn("hx-delete", payment)
        self.assertIn('hx-swap="innerHTML"', payment)
        self.assertIn("issueRequest(true)", detail)
        self.assertIn("__hunterHtmxConfirmBound", detail)
        self.assertIn("item.closest('.hidden')", detail)
