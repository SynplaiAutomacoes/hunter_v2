from __future__ import annotations

from datetime import date

from django.db import migrations

REFERENCE_DATE = date(2026, 8, 1)
REFERENCE_YEAR = 2026
REFERENCE_MONTH = 8


def _regenerate_august_2026_commissions(apps, schema_editor) -> None:
    from apps.collaborators.commission.orchestrator import WorkOrderCommissionOrchestrator
    from apps.collaborators.models import CollaboratorCommissionEntry, CollaboratorPayroll, WorkshopCollaborator
    from apps.collaborators.services import sync_collaborator_commission_entries, sync_collaborator_payroll
    from apps.workorder.models import WorkOrder, WorkOrderStatus

    orchestrator = WorkOrderCommissionOrchestrator()
    collaborator_ids: set[int] = set()

    workorders = (
        WorkOrder.objects.filter(status=WorkOrderStatus.APPROVED)
        .select_related("budget", "workshop")
        .prefetch_related("payments", "collaborators", "collaborators__commission_rules")
        .order_by("id")
    )
    for workorder in workorders:
        budget_type = getattr(workorder.budget, "budget_type", "") if workorder.budget_id else workorder.budget_type
        if str(budget_type or "").lower() != "sale":
            continue
        entries = orchestrator.generate_commissions_for_workorder(workorder=workorder)
        for entry in entries:
            if entry.reference_year == REFERENCE_YEAR and entry.reference_month == REFERENCE_MONTH:
                collaborator_ids.add(entry.collaborator_id)

    collaborator_ids.update(
        CollaboratorCommissionEntry.objects.filter(
            reference_year=REFERENCE_YEAR,
            reference_month=REFERENCE_MONTH,
        ).values_list("collaborator_id", flat=True)
    )
    collaborator_ids.update(
        CollaboratorPayroll.objects.filter(
            reference_year=REFERENCE_YEAR,
            reference_month=REFERENCE_MONTH,
        ).values_list("collaborator_id", flat=True)
    )

    for collaborator in WorkshopCollaborator.objects.filter(pk__in=collaborator_ids).order_by("id"):
        sync_collaborator_commission_entries(
            collaborator=collaborator,
            reference_date=REFERENCE_DATE,
            lock_reference=True,
        )
        sync_collaborator_payroll(
            collaborator=collaborator,
            reference_date=REFERENCE_DATE,
            lock_reference=True,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("collaborators", "0020_alter_collaboratorcommissionentry_commission_origin_and_more"),
        ("workorder", "0047_workorder_courtesy_reason_fields"),
    ]

    operations = [
        migrations.RunPython(_regenerate_august_2026_commissions, migrations.RunPython.noop),
    ]
