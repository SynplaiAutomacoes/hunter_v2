from django.db import migrations


def clamp_workorder_current_step(apps, schema_editor):
    WorkOrder = apps.get_model("workorder", "WorkOrder")
    WorkOrder.objects.filter(current_step__gt=4).update(current_step=4)


def reverse_clamp_workorder_current_step(apps, schema_editor):
    WorkOrder = apps.get_model("workorder", "WorkOrder")
    WorkOrder.objects.filter(status="approved", current_step=4).update(current_step=5)


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0047_remap_current_step_for_payments"),
    ]

    operations = [
        migrations.RunPython(clamp_workorder_current_step, reverse_clamp_workorder_current_step),
    ]
