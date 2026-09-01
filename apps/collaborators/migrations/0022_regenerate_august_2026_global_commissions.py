from __future__ import annotations

from datetime import date

from django.db import migrations

REFERENCE_DATE = date(2026, 8, 1)
REFERENCE_YEAR = 2026
REFERENCE_MONTH = 8

GLOBAL_COMMISSION_ORIGINS = (
    "service_global",
    "product_global",
)


def _regenerate_august_2026_global_commissions(apps, schema_editor) -> None:
    from apps.collaborators.commission.allocation import CommissionAllocationService
    from apps.collaborators.commission.orchestrator import WorkOrderCommissionOrchestrator
    from apps.collaborators.models import CollaboratorCommissionEntry, CollaboratorCommissionRule, WorkshopCollaborator
    from apps.collaborators.services import sync_collaborator_commission_entries, sync_collaborator_payroll
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

    global_collaborators = list(
        WorkshopCollaborator.objects.filter(pk__in=global_collaborator_ids, is_active=True)
        .select_related("workshop")
        .order_by("id")
    )
    workshop_ids = {collaborator.workshop_id for collaborator in global_collaborators}

    CollaboratorCommissionEntry.objects.filter(
        collaborator_id__in=global_collaborator_ids,
        reference_year=REFERENCE_YEAR,
        reference_month=REFERENCE_MONTH,
        status=CollaboratorCommissionEntry.Status.FORECAST,
        commission_origin__in=GLOBAL_COMMISSION_ORIGINS,
    ).exclude(origin=CollaboratorCommissionEntry.Origin.MANUAL).delete()

    workorder_ids: set[int] = set(
        WorkOrder.objects.filter(
            workshop_id__in=workshop_ids,
            status=WorkOrderStatus.APPROVED,
            budget_type="sale",
        ).values_list("id", flat=True)
    )

    # Reprocessa O.S. de venda que originaram garantias/cortesias abertas em agosto,
    # pois o prejuízo global usa as comissões registradas na O.S. de origem.
    origin_workorder_ids = set(
        WorkOrder.objects.filter(
            workshop_id__in=workshop_ids,
            budget_type__in=("warranty", "courtesy"),
            warranty_origin_id__isnull=False,
            criado_em__year=REFERENCE_YEAR,
            criado_em__month=REFERENCE_MONTH,
        ).values_list("warranty_origin_id", flat=True)
    )
    workorder_ids |= origin_workorder_ids

    orchestrator = WorkOrderCommissionOrchestrator()
    workorders = (
        WorkOrder.objects.filter(pk__in=workorder_ids)
        .select_related("budget", "workshop")
        .prefetch_related("payments", "collaborators", "collaborators__commission_rules")
        .order_by("id")
    )
    for workorder in workorders:
        CommissionAllocationService.sync_for_workorder(workorder=workorder)
        orchestrator.generate_commissions_for_workorder(workorder=workorder)

    for collaborator in global_collaborators:
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
        ("collaborators", "0021_regenerate_august_2026_commissions"),
        ("workorder", "0047_workorder_courtesy_reason_fields"),
    ]

    operations = [
        migrations.RunPython(_regenerate_august_2026_global_commissions, migrations.RunPython.noop),
    ]
