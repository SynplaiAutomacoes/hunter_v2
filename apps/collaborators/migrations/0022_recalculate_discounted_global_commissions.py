from __future__ import annotations

from collections import defaultdict

from django.db import migrations


GLOBAL_COMMISSION_ORIGINS = (
    "service_global",
    "product_global",
)


def _recalculate_discounted_global_commissions(apps, schema_editor) -> None:
    from apps.collaborators.commission.orchestrator import WorkOrderCommissionOrchestrator
    from apps.collaborators.models import CollaboratorCommissionEntry, CollaboratorCommissionRule, WorkshopCollaborator
    from apps.collaborators.services import refresh_unpaid_payroll_commissions_for_references
    from apps.workorder.models import WorkOrder, WorkOrderStatus

    global_collaborator_ids = set(
        CollaboratorCommissionRule.objects.filter(
            apply_scope=CollaboratorCommissionRule.ApplyScope.GLOBAL,
            is_active=True,
            collaborator__is_active=True,
        ).values_list("collaborator_id", flat=True)
    )
    if not global_collaborator_ids:
        return

    collaborators = list(
        WorkshopCollaborator.objects.filter(pk__in=global_collaborator_ids, is_active=True)
        .select_related("workshop")
        .order_by("id")
    )
    references_by_collaborator: dict[int, set[tuple[int, int]]] = defaultdict(set)
    previous_entries = CollaboratorCommissionEntry.objects.filter(
        collaborator_id__in=global_collaborator_ids,
        commission_origin__in=GLOBAL_COMMISSION_ORIGINS,
        status=CollaboratorCommissionEntry.Status.FORECAST,
    ).values_list("collaborator_id", "reference_year", "reference_month")
    for collaborator_id, year, month in previous_entries:
        references_by_collaborator[collaborator_id].add((year, month))

    workshop_ids = {collaborator.workshop_id for collaborator in collaborators}
    workorders = (
        WorkOrder.objects.filter(
            workshop_id__in=workshop_ids,
            status=WorkOrderStatus.APPROVED,
            budget_type="sale",
        )
        .select_related("budget", "workshop")
        .prefetch_related("payments", "collaborators", "collaborators__commission_rules")
        .order_by("id")
    )
    orchestrator = WorkOrderCommissionOrchestrator()
    for workorder in workorders:
        orchestrator.generate_commissions_for_workorder(workorder=workorder)

    current_entries = CollaboratorCommissionEntry.objects.filter(
        collaborator_id__in=global_collaborator_ids,
        commission_origin__in=GLOBAL_COMMISSION_ORIGINS,
        status=CollaboratorCommissionEntry.Status.FORECAST,
    ).values_list("collaborator_id", "reference_year", "reference_month")
    for collaborator_id, year, month in current_entries:
        references_by_collaborator[collaborator_id].add((year, month))

    for collaborator in collaborators:
        refresh_unpaid_payroll_commissions_for_references(
            collaborator=collaborator,
            references=references_by_collaborator[collaborator.pk],
        )


class Migration(migrations.Migration):
    dependencies = [
        ("collaborators", "0021_regenerate_august_2026_commissions"),
    ]

    operations = [
        migrations.RunPython(
            _recalculate_discounted_global_commissions,
            migrations.RunPython.noop,
        ),
    ]
