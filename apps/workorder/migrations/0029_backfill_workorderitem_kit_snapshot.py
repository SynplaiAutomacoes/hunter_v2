from django.db import migrations


def backfill_kit_snapshot_frozen(apps, schema_editor):
    WorkOrderItem = apps.get_model("workorder", "WorkOrderItem")
    WorkOrderKitItemOverride = apps.get_model("workorder", "WorkOrderKitItemOverride")

    item_ids = (
        WorkOrderKitItemOverride.objects.values_list("workorder_item_id", flat=True).distinct()
    )
    updated = WorkOrderItem.objects.filter(id__in=item_ids).update(kit_snapshot_frozen=True)
    if schema_editor.connection.alias == "default":
        print(f"  Backfilled kit_snapshot_frozen=True for {updated} WorkOrderItems")


class Migration(migrations.Migration):

    dependencies = [
        ("workorder", "0028_workorderitem_kit_snapshot_frozen"),
    ]

    operations = [
        migrations.RunPython(backfill_kit_snapshot_frozen, migrations.RunPython.noop),
    ]
