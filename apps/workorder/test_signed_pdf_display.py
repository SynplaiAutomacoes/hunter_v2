from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.budget.models import Budget
from apps.workorder.models import WorkOrder, WorkOrderSignatureStatus
from apps.workorder.util import (
    _build_customer_approvement_context,
    _build_edit_items_context,
    _build_workorder_pdf_modal_context,
    workorder_can_toggle_signed_pdf,
)
from apps.workshops.models.workshops import Workshop


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "workorder" / "partials"


class WorkOrderSignedPdfUrlTests(SimpleTestCase):
    def test_approved_signature_defaults_to_signed_workorder_pdf(self) -> None:
        workorder = SimpleNamespace(
            pk=685,
            signature_request_status=WorkOrderSignatureStatus.APPROVED,
            signature_external_id="env-685",
            signature_document_id="env-685",
        )
        self.assertTrue(workorder_can_toggle_signed_pdf(workorder))
        urls = _build_workorder_pdf_modal_context(workorder)
        pdf_view_url = reverse("workorder:visualizar_pdf", args=[685])
        self.assertTrue(urls["can_toggle_signed_pdf"])
        self.assertEqual(urls["initial_pdf_variant"], "signed")
        self.assertEqual(urls["initial_pdf_url"], f"{pdf_view_url}?variant=signed")
        self.assertEqual(urls["signed_pdf_url"], f"{pdf_view_url}?variant=signed")

    def test_without_signature_ids_stays_on_base_pdf(self) -> None:
        workorder = SimpleNamespace(
            pk=10,
            signature_request_status=WorkOrderSignatureStatus.SENT,
            signature_external_id="",
            signature_document_id="",
        )
        self.assertFalse(workorder_can_toggle_signed_pdf(workorder))
        urls = _build_workorder_pdf_modal_context(workorder)
        self.assertEqual(urls["initial_pdf_variant"], "base")
        self.assertIn("variant=base", str(urls["initial_pdf_url"]))

    def test_sent_signature_does_not_offer_signed_pdf_before_approval(self) -> None:
        workorder = SimpleNamespace(
            pk=11,
            signature_request_status=WorkOrderSignatureStatus.SENT,
            signature_external_id="env-11",
            signature_document_id="env-11",
        )

        self.assertFalse(workorder_can_toggle_signed_pdf(workorder))
        urls = _build_workorder_pdf_modal_context(workorder)
        self.assertFalse(urls["can_toggle_signed_pdf"])
        self.assertEqual(urls["initial_pdf_variant"], "base")


class WorkOrderSignedPdfTemplateTests(SimpleTestCase):
    def test_delivery_section_uses_workorder_signed_pdf_urls(self) -> None:
        template = (TEMPLATES_DIR / "customer_approvement_section.html").read_text(encoding="utf-8")
        self.assertIn("workorder_pdf_urls.signed_pdf_url", template)
        self.assertIn("workorder_pdf_urls.initial_pdf_url", template)
        self.assertNotIn("budget:visualizar_pdf_assinatura", template)


class WorkOrderResumeSignedPdfTests(TestCase):
    def setUp(self) -> None:
        self.workshop = Workshop.objects.create(
            name="Oficina PDF Assinado",
            cnpj="12.345.678/0001-93",
            phone="+5511999999993",
            address="Rua PDF, 1",
        )
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 8, 24))
        self.workorder = WorkOrder.objects.create(workshop=self.workshop, budget=self.budget)
        self.workorder.signature_request_status = WorkOrderSignatureStatus.APPROVED
        self.workorder.signature_external_id = "env-os-signed"
        self.workorder.signature_document_id = "env-os-signed"
        self.workorder.save(update_fields=["signature_request_status", "signature_external_id", "signature_document_id"])

    def test_resume_cliente_pdf_opens_signed_workorder_document(self) -> None:
        context = _build_edit_items_context(self.workorder)
        pdf_urls = context["resume_pdf_urls"]
        pdf_view_url = reverse("workorder:visualizar_pdf", args=[self.workorder.pk])
        self.assertTrue(pdf_urls["can_toggle_signed_pdf"])
        self.assertEqual(pdf_urls["initial_pdf_variant"], "signed")
        self.assertEqual(pdf_urls["cliente_url"], f"{pdf_view_url}?variant=signed")
        self.assertNotIn("/budget/", str(pdf_urls["cliente_url"]))

    def test_delivery_context_exposes_signed_workorder_pdf(self) -> None:
        context = _build_customer_approvement_context(self.workorder)
        pdf_urls = context["workorder_pdf_urls"]
        self.assertTrue(pdf_urls["can_toggle_signed_pdf"])
        self.assertIn("variant=signed", str(pdf_urls["initial_pdf_url"]))
