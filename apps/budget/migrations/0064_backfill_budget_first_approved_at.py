from django.db import migrations
from django.db.models import F


def backfill_first_approved_at(apps, schema_editor) -> None:
    Budget = apps.get_model("budget", "Budget")
    Budget.objects.filter(status="approved", first_approved_at__isnull=True).update(first_approved_at=F("atualizado_em"))


def noop_reverse(apps, schema_editor) -> None:
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("budget", "0063_budget_first_approved_at"),
    ]

    operations = [
        migrations.RunPython(backfill_first_approved_at, noop_reverse),
    ]
