from __future__ import annotations

from django.conf import settings
from django.db import migrations


def _is_production_environment() -> bool:
    env = str(getattr(settings, "ENVIRONMENT", "") or "").strip().strip("\"'").casefold()
    return env in {"production", "prod"}


def forwards_realign_accepts_messages(apps, schema_editor) -> None:
    """
    Realinha valores já existentes após 0019 (ambientes que já aplicaram o AddField).
    Em prod/production → True; fora → False.
    """
    Customer = apps.get_model("customer", "Customer")
    Customer.objects.all().update(accepts_messages=_is_production_environment())


class Migration(migrations.Migration):
    dependencies = [
        ("customer", "0020_review_plan_and_messaging_updates"),
    ]

    operations = [
        migrations.RunPython(forwards_realign_accepts_messages, migrations.RunPython.noop),
    ]
