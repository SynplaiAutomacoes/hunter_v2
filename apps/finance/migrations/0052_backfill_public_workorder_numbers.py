# Generated manually to replace internal work order PKs by the public OS number

from __future__ import annotations

from django.db import migrations

from apps.finance.migrations._workorder_number_backfill import backfill_workorder_movement_descriptions, rename_workorder_sources


def _backfill_movement_descriptions(apps, schema_editor) -> None:
    backfill_workorder_movement_descriptions(financial_movement_model=apps.get_model("finance", "FinancialMovement"))


def _rename_sources(apps, schema_editor) -> None:
    rename_workorder_sources(
        source_model=apps.get_model("sources", "Source"),
        financial_movement_model=apps.get_model("finance", "FinancialMovement"),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0051_nfe_transport_support"),
        ("sources", "0001_initial"),
        ("budget", "0069_merge_budget_cancellation_responsible"),
        ("workorder", "0046_leftover_courtesy_reason_default"),
    ]

    operations = [
        migrations.RunPython(_backfill_movement_descriptions, migrations.RunPython.noop),
        migrations.RunPython(_rename_sources, migrations.RunPython.noop),
    ]
