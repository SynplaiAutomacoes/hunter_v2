from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workshops", "0028_oil_change_tracking"),
    ]

    operations = [
        migrations.AddField(
            model_name="workshop",
            name="outbound_business_hours_enabled",
            field=models.BooleanField(default=True, verbose_name="Respeitar horário de disparo"),
        ),
        migrations.AddField(
            model_name="workshop",
            name="outbound_business_weekdays",
            field=models.CharField(
                default="0,1,2,3,4",
                help_text="Dias da semana (Python: Mon=0 … Sun=6), separados por vírgula.",
                max_length=32,
                verbose_name="Dias de disparo",
            ),
        ),
        migrations.AddField(
            model_name="workshop",
            name="outbound_business_start_hour",
            field=models.PositiveSmallIntegerField(
                default=8,
                help_text="Hora inicial inclusiva (0–23).",
                verbose_name="Hora inicial",
            ),
        ),
        migrations.AddField(
            model_name="workshop",
            name="outbound_business_end_hour",
            field=models.PositiveSmallIntegerField(
                default=18,
                help_text="Hora final exclusiva (0–23).",
                verbose_name="Hora final",
            ),
        ),
    ]
