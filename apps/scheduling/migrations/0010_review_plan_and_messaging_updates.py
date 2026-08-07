# Generated manually — preserve existing alert_lead_time values into alert_lead_times

import django.contrib.postgres.fields
from django.db import migrations, models


ALERT_LEAD_TIME_CHOICES = [
    (30, "30 minutos"),
    (60, "1 hora"),
    (120, "2 horas"),
    (180, "3 horas"),
    (300, "5 horas"),
    (1440, "1 dia"),
    (2880, "2 dias"),
    (10080, "1 semana"),
]


def copy_alert_lead_time_to_array(apps, schema_editor):
    Appointment = apps.get_model("scheduling", "Appointment")
    for appointment in Appointment.objects.all().iterator():
        lead_time = getattr(appointment, "alert_lead_time", None)
        if lead_time:
            appointment.alert_lead_times = [int(lead_time)]
            appointment.save(update_fields=["alert_lead_times"])


def noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("scheduling", "0009_messaging_history_outbound_and_alert_lead"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="alert_lead_times",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.PositiveIntegerField(choices=ALERT_LEAD_TIME_CHOICES),
                blank=True,
                default=list,
                help_text="Minutos antes do início do agendamento para enviar o alerta. É possível selecionar mais de uma opção.",
                verbose_name="Antecedência do alerta",
            ),
        ),
        migrations.RunPython(copy_alert_lead_time_to_array, noop_reverse),
        migrations.RemoveField(
            model_name="appointment",
            name="alert_lead_time",
        ),
    ]
