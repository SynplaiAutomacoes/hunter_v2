from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.budget.models import BudgetPdfRenderJob
from apps.budget.pdf_jobs import process_budget_pdf_job


class Command(BaseCommand):
    help = "Processa PDFs pendentes dos orçamentos em background."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options) -> None:
        limit = int(options.get("limit") or 20)
        processed = 0
        failed = 0

        jobs = BudgetPdfRenderJob.objects.filter(status=BudgetPdfRenderJob.Status.PENDING).select_related("budget").order_by("criado_em", "pk")[:limit]
        for job in jobs:
            processed_job = process_budget_pdf_job(job=job)
            if processed_job.status == BudgetPdfRenderJob.Status.COMPLETED:
                processed += 1
            elif processed_job.status == BudgetPdfRenderJob.Status.FAILED:
                failed += 1

        self.stdout.write(self.style.SUCCESS(f"PDFs processados: {processed}. Falhas: {failed}."))
