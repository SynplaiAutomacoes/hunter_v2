from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workorder", "0027_add_workorder_discount_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorderitem",
            name="kit_snapshot_frozen",
            field=models.BooleanField(default=False, verbose_name="Kit snapshot frozen"),
        ),
    ]
