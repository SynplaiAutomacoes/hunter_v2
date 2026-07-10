from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0034_merge_0032_service_shipping_0033_backfill"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorderitem",
            name="is_customer_supplied",
            field=models.BooleanField(default=False, verbose_name="Peça trazida pelo cliente"),
        ),
    ]
