from datetime import time

from django.db import migrations, models


def forwards_hours_to_times(apps, schema_editor) -> None:
    Workshop = apps.get_model("workshops", "Workshop")
    for workshop in Workshop.objects.all().iterator():
        start_hour = int(getattr(workshop, "outbound_business_start_hour", 8) or 8)
        end_hour = int(getattr(workshop, "outbound_business_end_hour", 18) or 18)
        workshop.outbound_business_start_time = time(hour=max(0, min(start_hour, 23)))
        workshop.outbound_business_end_time = time(hour=max(0, min(end_hour, 23)))
        workshop.save(update_fields=["outbound_business_start_time", "outbound_business_end_time"])


def backwards_times_to_hours(apps, schema_editor) -> None:
    Workshop = apps.get_model("workshops", "Workshop")
    for workshop in Workshop.objects.all().iterator():
        start = getattr(workshop, "outbound_business_start_time", None) or time(8, 0)
        end = getattr(workshop, "outbound_business_end_time", None) or time(18, 0)
        workshop.outbound_business_start_hour = int(start.hour)
        workshop.outbound_business_end_hour = int(end.hour)
        workshop.save(update_fields=["outbound_business_start_hour", "outbound_business_end_hour"])


class Migration(migrations.Migration):
    dependencies = [
        ("workshops", "0032_workshop_outbound_business_hours"),
    ]

    operations = [
        migrations.AddField(
            model_name="workshop",
            name="outbound_business_start_time",
            field=models.TimeField(
                default=time(8, 0),
                help_text="Horário inicial inclusivo da janela de envio.",
                verbose_name="Hora inicial",
            ),
        ),
        migrations.AddField(
            model_name="workshop",
            name="outbound_business_end_time",
            field=models.TimeField(
                default=time(18, 0),
                help_text="Horário final exclusivo da janela de envio.",
                verbose_name="Hora final",
            ),
        ),
        migrations.RunPython(forwards_hours_to_times, backwards_times_to_hours),
        migrations.RemoveField(
            model_name="workshop",
            name="outbound_business_start_hour",
        ),
        migrations.RemoveField(
            model_name="workshop",
            name="outbound_business_end_hour",
        ),
    ]
