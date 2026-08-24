from django.db import migrations, models

from . import _idempotent


def backfill_current_step(apps, schema_editor):
    WorkOrder = apps.get_model("workorder", "WorkOrder")
    WorkOrder.objects.filter(status="approved").update(current_step=4)
    WorkOrder.objects.filter(status="waiting_delivery").update(current_step=4)
    WorkOrder.objects.filter(status="waiting_collaborator").update(current_step=2)


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0044_migrate_waiting_delivery_to_draft"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workorder",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Aprovado"),
                    ("waiting_collaborator", "Aguardando Colaborador"),
                    ("waiting_delivery", "Aguardando Entrega"),
                    ("approved", "Veículo Entregue"),
                    ("rejected", "Reprovado"),
                    ("cancelled", "Cancelado"),
                ],
                default="draft",
                max_length=32,
                verbose_name="Status",
            ),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="workorder",
            name="current_step",
            field=models.PositiveSmallIntegerField(default=1, verbose_name="Etapa atual"),
        ),
        migrations.RunPython(backfill_current_step, reverse_code=migrations.RunPython.noop),
    ]
