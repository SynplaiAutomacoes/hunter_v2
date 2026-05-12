from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0019_workorder_reopen_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorder",
            name="cancellation_reason",
            field=models.TextField(blank=True, verbose_name="Justificativa do cancelamento"),
        ),
        migrations.AddField(
            model_name="workorder",
            name="rejection_reason",
            field=models.TextField(blank=True, verbose_name="Justificativa da rejeicao"),
        ),
    ]
