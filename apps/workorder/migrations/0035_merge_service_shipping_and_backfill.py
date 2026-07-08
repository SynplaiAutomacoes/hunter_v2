from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0033_workorderitem_service_shipping_and_more"),
        ("workorder", "0034_backfill_workorderitem_item_benefit_type"),
    ]

    operations = []
