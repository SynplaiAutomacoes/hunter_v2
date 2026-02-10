from __future__ import annotations

import datetime

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0011_alter_kit_atualizado_em_alter_kit_criado_em_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="kitservice",
            name="duration",
            field=models.DurationField(default=datetime.timedelta, verbose_name="Duração"),
        ),
    ]
