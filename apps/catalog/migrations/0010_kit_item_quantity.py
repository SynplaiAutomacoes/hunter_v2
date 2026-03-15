from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0009_kit"),
    ]

    operations = [
        migrations.AddField(
            model_name="kitproduct",
            name="quantity",
            field=models.PositiveIntegerField(default=1, verbose_name="Quantidade"),
        ),
        migrations.AddField(
            model_name="kitservice",
            name="quantity",
            field=models.PositiveIntegerField(default=1, verbose_name="Quantidade"),
        ),
    ]
