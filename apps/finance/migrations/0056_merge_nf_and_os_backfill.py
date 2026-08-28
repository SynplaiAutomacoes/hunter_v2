# Generated manually to join NF purchase-return chain with OS number backfill.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0052_backfill_public_workorder_numbers"),
        ("finance", "0055_repair_purchase_return_item_kind"),
    ]

    operations: list = []
