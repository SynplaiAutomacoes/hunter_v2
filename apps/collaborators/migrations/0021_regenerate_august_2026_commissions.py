from __future__ import annotations

from datetime import date

from django.db import migrations

REFERENCE_DATE = date(2026, 8, 1)
REFERENCE_YEAR = 2026
REFERENCE_MONTH = 8


def _cleanup_duplicate_zero_pool_commissions(apps, schema_editor) -> None:
    entry_model = apps.get_model("collaborators", "CollaboratorCommissionEntry")

    duplicate_ids: list[int] = []
    paid_pairs = entry_model.objects.filter(status="PAID").values("workorder_id", "collaborator_id").distinct()
    for pair in paid_pairs:
        entries = list(
            entry_model.objects.filter(
                workorder_id=pair["workorder_id"],
                collaborator_id=pair["collaborator_id"],
                status="PAID",
            ).order_by("id")
        )
        if len(entries) < 2:
            continue
        legacy_entries = [entry for entry in entries if not entry.commission_origin]
        pool_zero_entries = [
            entry
            for entry in entries
            if entry.commission_origin == "service_pct_pool" and (entry.commission_amount or 0) == 0
        ]
        if legacy_entries and pool_zero_entries:
            duplicate_ids.extend(entry.pk for entry in pool_zero_entries)

    if duplicate_ids:
        entry_model.objects.filter(pk__in=duplicate_ids).delete()


def _regenerate_august_2026_commissions(apps, schema_editor) -> None:
    from apps.collaborators.commission.allocation import CommissionAllocationService
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
        CommissionAllocationService.sync_for_workorder(workorder=workorder)
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
        ("workorder", "0055_merge_warranty_origin_and_os_tip"),
        ("finance", "0066_merge_fiscaldocument_options_and_partial_payment"),
    ]

    operations = [
        migrations.RunPython(_cleanup_duplicate_zero_pool_commissions, migrations.RunPython.noop),
        migrations.RunPython(_regenerate_august_2026_commissions, migrations.RunPython.noop),
    ]
