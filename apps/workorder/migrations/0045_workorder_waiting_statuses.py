from django.db import migrations, models


def migrate_existing_open_workorders(apps, schema_editor):
    WorkOrder = apps.get_model("workorder", "WorkOrder")
    WorkOrder.objects.filter(status="draft").update(status="waiting_delivery", current_step=3)
    WorkOrder.objects.filter(status="approved", current_step__gt=4).update(current_step=4)


def reverse_existing_open_workorders(apps, schema_editor):
    WorkOrder = apps.get_model("workorder", "WorkOrder")
    WorkOrder.objects.filter(status__in=["waiting_collaborator", "waiting_delivery"]).update(status="draft")


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0044_workorder_current_step"),
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
        migrations.RunPython(migrate_existing_open_workorders, reverse_existing_open_workorders),
    ]
