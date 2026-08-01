# Generated manually — replace %%nome_oficina%% with %%nome_fantasia%% in stored messages

from __future__ import annotations

import re

from django.db import migrations

_TOKEN_RE = re.compile(r"%%nome_oficina%%", re.IGNORECASE)
NEW_TOKEN = "%%nome_fantasia%%"


def replace_nome_oficina_tokens(apps, schema_editor):
    MessageTemplate = apps.get_model("messaging", "MessageTemplate")
    CustomerMessageGroup = apps.get_model("messaging", "CustomerMessageGroup")

    for model in (MessageTemplate, CustomerMessageGroup):
        for row in model.objects.filter(message__icontains="nome_oficina").iterator():
            message = str(row.message or "")
            updated = _TOKEN_RE.sub(NEW_TOKEN, message)
            if updated != message:
                row.message = updated
                row.save(update_fields=["message"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("messaging", "0009_review_plan_and_messaging_updates"),
    ]

    operations = [
        migrations.RunPython(replace_nome_oficina_tokens, noop_reverse),
    ]
