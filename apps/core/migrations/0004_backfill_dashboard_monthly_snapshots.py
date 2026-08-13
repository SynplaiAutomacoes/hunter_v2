from __future__ import annotations

from django.db import migrations


def forwards_backfill_dashboard_snapshots(apps: object, schema_editor: object) -> None:
    """Freeze current live dashboard KPIs for every already-closed month with activity.

    Uses the live service (not historical models) because metrics depend on pricing,
    DRE markup, and denormalized totals that historical migration state cannot reproduce.
    """
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM workshops_workshop")
        workshop_count = int(cursor.fetchone()[0])
    if workshop_count == 0:
        return

    from apps.core.infrastructure.services.dashboard_snapshot_service import backfill_closed_snapshots

    created = backfill_closed_snapshots()
    print(f"Dashboard monthly snapshots created: {created}")


def backwards_delete_dashboard_snapshots(apps: object, schema_editor: object) -> None:
    DashboardMonthlySnapshot = apps.get_model("core", "DashboardMonthlySnapshot")
    DashboardMonthlySnapshot.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_dashboard_monthly_snapshot"),
    ]

    operations = [
        migrations.RunPython(forwards_backfill_dashboard_snapshots, backwards_delete_dashboard_snapshots),
    ]
