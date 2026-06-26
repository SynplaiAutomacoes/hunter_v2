from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workorder", "0029_backfill_workorderitem_kit_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorder",
            name="observations",
            field=models.TextField(blank=True, default="", verbose_name="Observações"),
        ),
    ]
