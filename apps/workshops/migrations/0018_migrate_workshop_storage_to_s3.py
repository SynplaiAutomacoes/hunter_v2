from __future__ import annotations

import secrets

from django.db import migrations, models

import apps.workshops.models.workshops


def populate_logo_public_tokens(apps, schema_editor) -> None:
    Workshop = apps.get_model("workshops", "Workshop")
    for workshop in Workshop.objects.all().only("id", "logo_public_token"):
        if workshop.logo_public_token:
            continue
        workshop.logo_public_token = secrets.token_hex(16)
        workshop.save(update_fields=["logo_public_token"])


class Migration(migrations.Migration):
    dependencies = [
        ("workshops", "0017_workshop_certificate_content_type_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="workshop",
            name="certificate_file_key",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.AddField(
            model_name="workshop",
            name="logo_file_key",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.AddField(
            model_name="workshop",
            name="logo_public_token",
            field=models.CharField(blank=True, default="", editable=False, max_length=32),
        ),
        migrations.RunPython(populate_logo_public_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="workshop",
            name="logo_public_token",
            field=models.CharField(default=apps.workshops.models.workshops.generate_workshop_logo_public_token, editable=False, max_length=32, unique=True),
        ),
        migrations.RemoveField(
            model_name="workshop",
            name="certificate_mongo_file_id",
        ),
        migrations.RemoveField(
            model_name="workshop",
            name="logo",
        ),
        migrations.RemoveField(
            model_name="workshop",
            name="logo_mongo_file_id",
        ),
        migrations.RemoveField(
            model_name="workshop",
            name="pfx_certificate",
        ),
    ]
