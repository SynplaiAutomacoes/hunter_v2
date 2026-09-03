from __future__ import annotations

from django.db import migrations


def _backfill_global_collaborators_in_workorders(apps, schema_editor) -> None:
    rule_model = apps.get_model("collaborators", "CollaboratorCommissionRule")
    workorder_model = apps.get_model("workorder", "WorkOrder")

    # Todas as regras globais ativas
    global_rules = list(
        rule_model.objects.filter(
            apply_scope="global",
            is_active=True,
        ).select_related("collaborator")
    )

    for rule in global_rules:
        collaborator = rule.collaborator
        if not collaborator:
            continue
        workshop_id = getattr(collaborator, "workshop_id", None)
        if not workshop_id:
            continue

        workorders = workorder_model.objects.filter(
            workshop_id=workshop_id,
            budget_type="sale",
            status="approved",
            criado_em__gte=rule.criado_em,
        )

        for workorder in workorders.iterator(chunk_size=200):
            workorder.collaborators.add(collaborator)


class Migration(migrations.Migration):
    dependencies = [
        ("collaborators", "0022_recalculate_discounted_global_commissions"),
    ]

    operations = [
        migrations.RunPython(
            _backfill_global_collaborators_in_workorders,
            migrations.RunPython.noop,
        ),
    ]
