from django.db import migrations


def remap_workorder_current_step(apps, schema_editor):
    WorkOrder = apps.get_model("workorder", "WorkOrder")
    WorkOrder.objects.filter(current_step=4).update(current_step=5)
    WorkOrder.objects.filter(current_step=3).update(current_step=4)


def reverse_remap_workorder_current_step(apps, schema_editor):
    WorkOrder = apps.get_model("workorder", "WorkOrder")
    WorkOrder.objects.filter(current_step=4).update(current_step=3)
    WorkOrder.objects.filter(current_step=5).update(current_step=4)


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0046_merge_20260815_1956"),
    ]

    operations = [
        migrations.RunPython(remap_workorder_current_step, reverse_remap_workorder_current_step),
    ]
