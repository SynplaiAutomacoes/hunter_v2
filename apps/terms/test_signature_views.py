from __future__ import annotations

from unittest.mock import patch

from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.budget.models import Budget, SignatureStatus
from apps.core.domain.contracts.documents import DocumentPayload
from apps.core.infrastructure.providers import get_signature_service
from apps.core.infrastructure.services.signature_webhook import (
    SignatureWebhookView,
    build_synplaisign_webhook_signature,
    process_signature_webhook_payload,
)
from apps.core.infrastructure.services.webmania.webmania_secrets import encrypt_secret
from apps.terms.models import BudgetTermSigning, TermTemplateType, WorkshopTermTemplate
from apps.terms.services.signature import (
    BUDGET_TERM_SIGNATURE_DOCUMENT_ID_KEY,
    BUDGET_TERM_SIGNATURE_TOKEN_SALT,
)


class BudgetTermSignatureViewTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        account = Account.objects.create(name="Conta Termo Assinatura")
        from apps.workshops.models.workshops import Workshop

        self.workshop = Workshop.objects.create(
            account=account,
            name="Oficina Termo",
            cnpj="11.222.333/0001-44",
            phone="+5511777777777",
            address="Rua Termo, 1",
        )
        self.term_template = WorkshopTermTemplate.objects.create(
            workshop=self.workshop,
            template_type=TermTemplateType.VEHICLE_RECEIPT,
            name="Recebimento",
            document_title="TERMO DE RECEBIMENTO",
            is_default=True,
            content={"sections": [{"title": "P1", "topics": []}]},
        )
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date="2026-08-30", number=1, slider=0)
        self.signing = BudgetTermSigning.objects.create(budget=self.budget, term_template=self.term_template)
        self.signing.regenerate_signature_token()

    def _build_token(self, *, version: int | None = None) -> str:
        return get_signature_service().build_signature_token(
            token_salt=BUDGET_TERM_SIGNATURE_TOKEN_SALT,
            document_id_key=BUDGET_TERM_SIGNATURE_DOCUMENT_ID_KEY,
            document_id=self.signing.pk,
            version=self.signing.signature_token_version if version is None else version,
        )

    def test_budget_term_signature_preview_returns_200(self) -> None:
        token = self._build_token()
        response = self.client.get(reverse("terms:budget_term_signature_preview", kwargs={"token": token}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TERMO DE RECEBIMENTO")

    @patch("apps.terms.views.render_term_pdf_document")
    def test_budget_term_signature_file_returns_200(self, render_mock) -> None:
        render_mock.return_value = DocumentPayload(content=b"%PDF-1.4 test", filename="termo.pdf")
        token = self._build_token()
        response = self.client.get(reverse("terms:budget_term_signature_file", kwargs={"token": token}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_budget_term_signature_preview_wrong_version_returns_404(self) -> None:
        token = self._build_token(version=self.signing.signature_token_version + 99)
        response = self.client.get(reverse("terms:budget_term_signature_preview", kwargs={"token": token}))
        self.assertEqual(response.status_code, 404)

    @patch("apps.terms.views.render_term_pdf_document")
    def test_budget_term_signature_file_wrong_version_returns_404(self, render_mock) -> None:
        token = self._build_token(version=self.signing.signature_token_version + 99)
        response = self.client.get(reverse("terms:budget_term_signature_file", kwargs={"token": token}))
        self.assertEqual(response.status_code, 404)
        render_mock.assert_not_called()

    @patch("apps.terms.views.download_signed_pdf", return_value=b"%PDF-1.4 signed")
    @patch("apps.terms.views.get_workshop_synplaisign_api_key", return_value="sk_test")
    def test_budget_term_signature_file_downloads_signed_pdf_when_approved(self, _api_key_mock, _download_mock) -> None:
        self.signing.mark_signature_sent("env-term-1", document_id="doc-term-1")
        self.signing.mark_signature_approved()
        token = self._build_token()
        response = self.client.get(reverse("terms:budget_term_signature_file", kwargs={"token": token}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        _download_mock.assert_called_once()


class BudgetTermSignatureWebhookTests(TestCase):
    def setUp(self) -> None:
        account = Account.objects.create(name="Conta Webhook Termo")
        from apps.workshops.models.workshops import Workshop

        workshop = Workshop.objects.create(
            account=account,
            name="Oficina Webhook",
            cnpj="55.666.777/0001-88",
            phone="+5511666666666",
            address="Rua Webhook, 2",
        )
        term_template = WorkshopTermTemplate.objects.create(
            workshop=workshop,
            template_type=TermTemplateType.VEHICLE_RECEIPT,
            name="Recebimento",
            document_title="TERMO",
            is_default=True,
            content={"sections": []},
        )
        budget = Budget.objects.create(workshop=workshop, entry_date="2026-08-30", number=2, slider=0)
        self.signing = BudgetTermSigning.objects.create(budget=budget, term_template=term_template)
        self.signing.mark_signature_sent("env-term-webhook", document_id="doc-term-webhook")

    def test_envelope_completed_marks_budget_term_signing_approved(self) -> None:
        response = process_signature_webhook_payload(
            payload={"event": "ENVELOPE_COMPLETED", "envelopeId": "env-term-webhook"},
        )
        self.assertEqual(response.status_code, 200)
        self.signing.refresh_from_db()
        self.assertEqual(self.signing.signature_request_status, SignatureStatus.APPROVED)


class BudgetTermSignatureWebhookViewTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.view = SignatureWebhookView.as_view()

        account = Account.objects.create(name="Conta Webhook View Termo")
        from apps.workshops.models.workshops import Workshop

        self.workshop = Workshop.objects.create(
            account=account,
            name="Oficina Webhook View",
            cnpj="99.888.777/0001-66",
            phone="+5511555555555",
            address="Rua View, 3",
        )
        self.workshop.synplaisign_webhook_secret = encrypt_secret("whsec_term_view")
        self.workshop.save(update_fields=["synplaisign_webhook_secret"])

        term_template = WorkshopTermTemplate.objects.create(
            workshop=self.workshop,
            template_type=TermTemplateType.VEHICLE_RECEIPT,
            name="Recebimento",
            document_title="TERMO",
            is_default=True,
            content={"sections": []},
        )
        budget = Budget.objects.create(workshop=self.workshop, entry_date="2026-08-30", number=3, slider=0)
        self.signing = BudgetTermSigning.objects.create(budget=budget, term_template=term_template)
        self.signing.mark_signature_sent("env-term-view", document_id="env-term-view")

    def test_webhook_view_accepts_hmac_and_marks_term_approved(self) -> None:
        import json

        body = json.dumps(
            {
                "event": "ENVELOPE_COMPLETED",
                "envelopeId": "env-term-view",
                "timestamp": "2026-08-30T21:00:00.000Z",
                "data": {"status": "SIGNED"},
            }
        ).encode("utf-8")
        signature = build_synplaisign_webhook_signature(body=body, secret="whsec_term_view")
        request = self.factory.post(
            "/budget/signature/webhook/",
            data=body,
            content_type="application/json",
            HTTP_X_SYNPLAI_SIGNATURE=signature,
            HTTP_X_SYNPLAI_EVENT="ENVELOPE_COMPLETED",
        )
        response = self.view(request)
        self.assertEqual(response.status_code, 200)
        self.signing.refresh_from_db()
        self.assertEqual(self.signing.signature_request_status, SignatureStatus.APPROVED)
