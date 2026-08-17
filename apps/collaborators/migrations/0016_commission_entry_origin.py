from django.db import migrations


def label_existing_entries_as_workorder_rate(apps, schema_editor):
    """Rótulo histórico: entradas legadas pertencem à origem "workorder_rate".

    Valores econômicos (base_amount/commission_amount/percentage) permanecem
    intactos — a migration apenas garante um rótulo consistente de origem.
    """
    CollaboratorCommissionEntry = apps.get_model("collaborators", "CollaboratorCommissionEntry")
    CollaboratorCommissionEntry.objects.exclude(
        commission_origin__in=[
            "workorder_rate",
            "service_rule",
            "product_rule",
        ]
    ).update(commission_origin="workorder_rate")


class Migration(migrations.Migration):

    dependencies = [
        ("collaborators", "0015_commission_rules_and_settings"),
    ]

    operations = [
        migrations.RunPython(label_existing_entries_as_workorder_rate, migrations.RunPython.noop),
    ]