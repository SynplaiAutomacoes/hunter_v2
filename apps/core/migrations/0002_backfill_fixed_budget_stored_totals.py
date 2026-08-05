from __future__ import annotations

from django.db import migrations


FIXED_BUDGET_TYPES = frozenset({"warranty", "courtesy"})


def forwards_backfill_fixed_stored_totals(apps: object, schema_editor: object) -> None:
    """Rebuild list totals for warranty/courtesy using current live pricing helpers.

    Imports the live service (not historical models) because operational totals
    depend on kit/benefit helpers that historical migration state cannot reproduce.

    Skip when there is nothing to rebuild: fresh/empty DBs (e.g. test creation)
    would otherwise fail because the live Workshop model expects columns that do
    not exist yet at this point in the migration graph.
    """
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM budget_budget WHERE budget_type IN ('warranty', 'courtesy')"
        )
        remaining = int(cursor.fetchone()[0])
    if remaining == 0:
        return

    from apps.core.infrastructure.services.stored_totals import backfill_stored_totals

    backfill_stored_totals(budget_types=FIXED_BUDGET_TYPES)


def backwards_noop(apps: object, schema_editor: object) -> None:
    # Rolling back would zero list totals again for fixed documents; leave as-is.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_create_editinglock"),
        ("budget", "0059_merge_0056_alter_0058_stored_totals"),
        ("workorder", "0037_wave2_stored_totals"),
    ]

    operations = [
        migrations.RunPython(forwards_backfill_fixed_stored_totals, backwards_noop),
    ]
