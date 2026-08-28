from django.db import migrations

from . import _idempotent


def ensure_courtesy_reason_default(apps, schema_editor):
    _idempotent.ensure_empty_string_default(
        schema_editor,
        table="workorder_workorder",
        columns=("courtesy_reason_description",),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0045_workorder_current_step_and_waiting_statuses"),
    ]

    operations = [
        migrations.RunPython(ensure_courtesy_reason_default, reverse_code=migrations.RunPython.noop),
    ]
