from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0032_workorderitem_service_shipping_and_more"),
        ("workorder", "0033_backfill_workorderitem_item_benefit_type"),
    ]

    operations = []
