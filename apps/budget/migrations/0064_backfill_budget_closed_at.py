from django.db import migrations
from django.db.models import F


CLOSED_STATUSES = ("approved", "rejected", "cancelled")


def backfill_closed_at(apps, schema_editor) -> None:
    Budget = apps.get_model("budget", "Budget")
    Budget.objects.filter(status__in=CLOSED_STATUSES, closed_at__isnull=True).update(closed_at=F("atualizado_em"))


def noop_reverse(apps, schema_editor) -> None:
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("budget", "0063_budget_closed_at"),
    ]

    operations = [
        migrations.RunPython(backfill_closed_at, noop_reverse),
    ]
