from __future__ import annotations

from pathlib import Path

from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone

from apps.budget.documents.provider import render_budget_pdf_document
from apps.budget.models import Budget, BudgetPdfRenderJob
from apps.budget.pdf_context import build_budget_pdf_context
from apps.core.infrastructure.pdf.pdf_engine import render_pdf_from_html


PDF_MANAGER_TEMPLATE = "budget/partials/pdf/visualizarPDFGestor.html"


def get_budget_pdf_job(*, budget: Budget, variant: str) -> BudgetPdfRenderJob:
    return BudgetPdfRenderJob.objects.get(budget=budget, variant=variant)


def get_or_queue_budget_pdf_job(*, budget: Budget, variant: str, requested_by=None) -> BudgetPdfRenderJob:
    budget_updated_at = getattr(budget, "atualizado_em", None)
    job, _ = BudgetPdfRenderJob.objects.get_or_create(
        budget=budget,
        variant=variant,
        defaults={
            "requested_by": requested_by,
            "budget_updated_at": budget_updated_at,
        },
    )

    is_stale = job.budget_updated_at != budget_updated_at
    needs_queue = job.status in {BudgetPdfRenderJob.Status.PENDING, BudgetPdfRenderJob.Status.PROCESSING}
    if job.status == BudgetPdfRenderJob.Status.COMPLETED and not is_stale and job.output_file:
        return job

    if job.status == BudgetPdfRenderJob.Status.FAILED:
        needs_queue = False

    if not needs_queue or is_stale or not job.output_file:
        if job.output_file:
            job.output_file.delete(save=False)
        job.status = BudgetPdfRenderJob.Status.PENDING
        job.requested_by = requested_by
        job.budget_updated_at = budget_updated_at
        job.completed_at = None
        job.error_message = ""
        job.output_file = ""
        job.save(update_fields=["status", "requested_by", "budget_updated_at", "completed_at", "error_message", "output_file", "atualizado_em"])

    return job


def is_budget_pdf_job_ready(*, budget: Budget, variant: str) -> bool:
    try:
        job = get_budget_pdf_job(budget=budget, variant=variant)
    except BudgetPdfRenderJob.DoesNotExist:
        return False

    return bool(job.status == BudgetPdfRenderJob.Status.COMPLETED and job.output_file and job.budget_updated_at == getattr(budget, "atualizado_em", None))


def _build_budget_pdf_bytes(*, budget: Budget, variant: str) -> bytes:
    if variant == BudgetPdfRenderJob.Variant.BASE:
        return render_budget_pdf_document(
            budget=budget,
            filename=f"orcamento_{budget.id}_base.pdf",
        ).content

    if variant == BudgetPdfRenderJob.Variant.MANAGER:
        context = build_budget_pdf_context(budget=budget, presentation="selected_items")
        html = render_to_string(PDF_MANAGER_TEMPLATE, context)
        return render_pdf_from_html(html)

    raise ValueError(f"Unsupported budget PDF variant: {variant}")


def process_budget_pdf_job(*, job: BudgetPdfRenderJob) -> BudgetPdfRenderJob:
    updated = BudgetPdfRenderJob.objects.filter(pk=job.pk, status=BudgetPdfRenderJob.Status.PENDING).update(
        status=BudgetPdfRenderJob.Status.PROCESSING,
        error_message="",
        atualizado_em=timezone.now(),
    )
    if updated == 0:
        return BudgetPdfRenderJob.objects.get(pk=job.pk)

    job.refresh_from_db()

    try:
        pdf_bytes = _build_budget_pdf_bytes(budget=job.budget, variant=job.variant)
    except Exception as exc:
        job.status = BudgetPdfRenderJob.Status.FAILED
        job.error_message = str(exc)
        job.completed_at = None
        job.save(update_fields=["status", "error_message", "completed_at", "atualizado_em"])
        return job

    file_name = f"budget-{job.budget_id}-{job.variant}-{timezone.now().strftime('%Y%m%d%H%M%S')}.pdf"
    if job.output_file:
        job.output_file.delete(save=False)
    job.output_file.save(Path(file_name).name, ContentFile(pdf_bytes), save=False)
    job.status = BudgetPdfRenderJob.Status.COMPLETED
    job.error_message = ""
    job.completed_at = timezone.now()
    job.save(update_fields=["status", "error_message", "completed_at", "output_file", "atualizado_em"])
    return job
