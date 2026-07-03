from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0052_add_snapshot_to_budgethistory"),
        ("budget", "0052_budgetitem_local_item_type"),
        ("budget", "0052_budgetitem_service_shipping_and_more"),
    ]

    operations = []
