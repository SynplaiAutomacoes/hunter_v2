# Generated manually — default alert_customer=True and lead times 1h/1d/2d

from django.contrib.postgres.fields import ArrayField
from django.db import migrations, models


def default_alert_lead_times():
    return [60, 1440, 2880]


class Migration(migrations.Migration):
    dependencies = [
        ("scheduling", "0010_review_plan_and_messaging_updates"),
    ]

    operations = [
        migrations.AlterField(
            model_name="appointment",
            name="alert_customer",
            field=models.BooleanField(default=True, verbose_name="Alertar cliente"),
        ),
        migrations.AlterField(
            model_name="appointment",
            name="alert_lead_times",
            field=ArrayField(
                base_field=models.PositiveIntegerField(
                    choices=[
                        (30, "30 minutos"),
                        (60, "1 hora"),
                        (120, "2 horas"),
                        (180, "3 horas"),
                        (300, "5 horas"),
                        (1440, "1 dia"),
                        (2880, "2 dias"),
                        (10080, "1 semana"),
                    ]
                ),
                blank=True,
                default=default_alert_lead_times,
                help_text="Minutos antes do início do agendamento para enviar o alerta. É possível selecionar mais de uma opção.",
                size=None,
                verbose_name="Antecedência do alerta",
            ),
        ),
    ]
