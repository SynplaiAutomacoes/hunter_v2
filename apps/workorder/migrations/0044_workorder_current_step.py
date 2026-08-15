from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0043_workorder_signature_decline_pending"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorder",
            name="current_step",
            field=models.PositiveSmallIntegerField(default=5, verbose_name="Etapa atual"),
        ),
        migrations.AlterField(
            model_name="workorder",
            name="current_step",
            field=models.PositiveSmallIntegerField(default=1, verbose_name="Etapa atual"),
        ),
    ]
