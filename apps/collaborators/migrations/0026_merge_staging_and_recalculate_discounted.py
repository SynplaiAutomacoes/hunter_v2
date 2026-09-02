from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("collaborators", "0024_merge_discounted_and_august_global_commissions"),
        ("collaborators", "0025_recalculate_discounted_global_commissions"),
    ]

    operations = []
