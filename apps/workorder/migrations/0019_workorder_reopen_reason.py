from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0018_workorder_unsigned_delivery_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorder",
            name="reopen_reason",
            field=models.TextField(blank=True, verbose_name="Justificativa da reabertura"),
        ),
    ]
