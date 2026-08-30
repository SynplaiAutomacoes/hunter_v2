from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.budget.models import SignatureStatus
from apps.terms.presenters.budget_term_modal import resolve_budget_term_modal_urls


class BudgetTermModalUrlsTests(SimpleTestCase):
    def test_resolve_urls_without_signing(self) -> None:
        urls = resolve_budget_term_modal_urls(budget_id=10, signing=None, term_template_id=3)
        self.assertFalse(urls.can_toggle_signed_pdf)
        self.assertIn("term_template=3", urls.base_pdf_url)
        self.assertIn("download=1", urls.base_download_url)

    def test_resolve_urls_with_sent_signing(self) -> None:
        signing = SimpleNamespace(
            signature_request_status=SignatureStatus.SENT,
            signature_external_id="env-1",
            signature_token_active=True,
            pk=5,
            signature_token_version=1,
        )
        urls = resolve_budget_term_modal_urls(budget_id=10, signing=signing, term_template_id=3)
        self.assertTrue(urls.can_toggle_signed_pdf)
        self.assertTrue(urls.is_signature_resend)
        self.assertIn("/terms/budget/signature-file/", urls.signed_pdf_url)
