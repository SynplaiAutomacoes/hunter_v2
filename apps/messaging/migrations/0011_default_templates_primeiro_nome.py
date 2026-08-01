# Generated manually — update seeded default templates to use %%primeiro_nome%%

from __future__ import annotations

from django.db import migrations

OLD_GREETING = "Oi %%nome%%, tudo bem?"
NEW_GREETING = "Oi %%primeiro_nome%%, tudo bem?"

SPECIAL_TYPES = ("birthday", "appointment", "review_plan", "satisfaction")


def switch_defaults_to_primeiro_nome(apps, schema_editor):
    MessageTemplate = apps.get_model("messaging", "MessageTemplate")
    for row in MessageTemplate.objects.filter(template_type__in=SPECIAL_TYPES, message__contains=OLD_GREETING).iterator():
        updated = (row.message or "").replace(OLD_GREETING, NEW_GREETING)
        if updated != row.message:
            row.message = updated
            row.save(update_fields=["message"])


def revert_defaults_to_nome(apps, schema_editor):
    MessageTemplate = apps.get_model("messaging", "MessageTemplate")
    for row in MessageTemplate.objects.filter(template_type__in=SPECIAL_TYPES, message__contains=NEW_GREETING).iterator():
        updated = (row.message or "").replace(NEW_GREETING, OLD_GREETING)
        if updated != row.message:
            row.message = updated
            row.save(update_fields=["message"])


class Migration(migrations.Migration):
    dependencies = [
        ("messaging", "0010_replace_nome_oficina_with_nome_fantasia"),
    ]

    operations = [
        migrations.RunPython(switch_defaults_to_primeiro_nome, revert_defaults_to_nome),
    ]
