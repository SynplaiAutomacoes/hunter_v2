from django.db import migrations, models


def forwards_migrate_pending(apps, schema_editor):
    MessageDispatchLog = apps.get_model("messaging", "MessageDispatchLog")
    MessageDispatchBatch = apps.get_model("messaging", "MessageDispatchBatch")

    MessageDispatchLog.objects.filter(status="pending").update(status="processing")
    for batch in MessageDispatchBatch.objects.all().iterator():
        pending = int(getattr(batch, "pending_count", 0) or 0)
        if pending:
            batch.processing_count = int(batch.processing_count or 0) + pending
            batch.pending_count = 0
            batch.save(update_fields=["processing_count", "pending_count"])


class Migration(migrations.Migration):

    dependencies = [
        ("messaging", "0005_add_processing_status_to_dispatch_log"),
    ]

    operations = [
        migrations.AddField(
            model_name="messagedispatchbatch",
            name="cancelled_count",
            field=models.PositiveIntegerField(default=0, verbose_name="Canceladas"),
        ),
        migrations.RunPython(forwards_migrate_pending, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="messagedispatchbatch",
            name="pending_count",
        ),
        migrations.AlterField(
            model_name="messagedispatchlog",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "Na fila"),
                    ("processing", "Processando"),
                    ("sent", "Enviada"),
                    ("failed", "Falhou"),
                    ("cancelled", "Cancelada"),
                ],
                default="queued",
                max_length=20,
                verbose_name="Status",
            ),
        ),
    ]
