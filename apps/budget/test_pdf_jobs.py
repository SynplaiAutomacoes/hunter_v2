from __future__ import annotations

from datetime import date
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import RequestFactory, TestCase

from apps.accounts.models import Account
from apps.budget.models import Budget, BudgetPdfRenderJob
from apps.budget.views.pdf_views import download_pdf_gestor, visualizar_pdf_assinatura
from apps.collaborators.models import WorkshopMember
from apps.iam.models import WorkshopRole
from apps.workshops.models.workshops import Workshop


User = get_user_model()


class BudgetPdfJobTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="budget-pdf", password="secret", cpf="12345678901")
        self.account = Account.objects.create(name="Conta PDF")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina PDF",
            cnpj="12.345.678/0001-90",
            phone="+5511999999999",
            address="Rua PDF, 123",
        )
        self.role = WorkshopRole.objects.create(account=self.account, name="Diretor")
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=self.role, is_active=True)
        self.budget = Budget.objects.create(workshop=self.workshop, entry_date=date(2026, 7, 6))

    def _build_request(self, path: str):
        request = self.factory.get(path)
        request.user = self.user
        request.session = {"active_workshop_id": self.workshop.pk}
        return request

    def test_budget_pdf_view_queues_background_job_when_pdf_is_missing(self) -> None:
        response = visualizar_pdf_assinatura(self._build_request(f"/budget/visualizar-pdf-assinatura/{self.budget.pk}"), self.budget.pk)

        self.assertEqual(response.status_code, 202)
        job = BudgetPdfRenderJob.objects.get(budget=self.budget, variant=BudgetPdfRenderJob.Variant.BASE)
        self.assertEqual(job.status, BudgetPdfRenderJob.Status.PENDING)

    def test_manager_download_queues_background_job_when_pdf_is_missing(self) -> None:
        response = download_pdf_gestor(self._build_request(f"/budget/download-pdf-gestor/{self.budget.pk}"), self.budget.pk)

        self.assertEqual(response.status_code, 202)
        job = BudgetPdfRenderJob.objects.get(budget=self.budget, variant=BudgetPdfRenderJob.Variant.MANAGER)
        self.assertEqual(job.status, BudgetPdfRenderJob.Status.PENDING)

    @patch("apps.budget.pdf_jobs.render_budget_pdf_document")
    def test_management_command_processes_pending_budget_pdf_jobs(self, render_budget_pdf_document_mock) -> None:
        render_budget_pdf_document_mock.return_value.content = b"%PDF-test-base"
        BudgetPdfRenderJob.objects.create(
            budget=self.budget,
            variant=BudgetPdfRenderJob.Variant.BASE,
            status=BudgetPdfRenderJob.Status.PENDING,
            requested_by=self.user,
            budget_updated_at=self.budget.atualizado_em,
        )

        stdout = StringIO()
        call_command("process_budget_pdf_jobs", "--limit", "10", stdout=stdout)

        job = BudgetPdfRenderJob.objects.get(budget=self.budget, variant=BudgetPdfRenderJob.Variant.BASE)
        self.assertEqual(job.status, BudgetPdfRenderJob.Status.COMPLETED)
        self.assertTrue(job.output_file.name.endswith(".pdf"))
        self.assertIn("PDFs processados: 1", stdout.getvalue())
