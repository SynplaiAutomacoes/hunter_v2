from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workshops", "0036_merge_20260731_1613"),
    ]

    operations = [
        migrations.AddField(
            model_name="workshop",
            name="synplaisign_api_key",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Armazenada criptografada. Criada automaticamente no cadastro da oficina.",
                max_length=512,
                verbose_name="SynplaiSign API Key",
            ),
        ),
        migrations.AddField(
            model_name="workshop",
            name="synplaisign_api_key_id",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="SynplaiSign API Key ID"),
        ),
        migrations.AddField(
            model_name="workshop",
            name="synplaisign_webhook_id",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="SynplaiSign Webhook ID"),
        ),
        migrations.AddField(
            model_name="workshop",
            name="synplaisign_webhook_secret",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Armazenado criptografado. Usado para validar HMAC dos callbacks.",
                max_length=512,
                verbose_name="SynplaiSign Webhook Secret",
            ),
        ),
    ]
