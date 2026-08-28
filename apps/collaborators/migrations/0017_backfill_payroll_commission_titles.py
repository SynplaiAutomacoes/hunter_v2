# Generated manually to replace internal work order PKs by the public OS number

from __future__ import annotations

from django.db import migrations

from apps.collaborators.migrations._payroll_commission_titles import backfill_commission_item_titles


def _backfill_commission_titles(apps, schema_editor) -> None:
    backfill_commission_item_titles(
        payroll_item_model=apps.get_model("collaborators", "CollaboratorPayrollItem"),
        workorder_model=apps.get_model("workorder", "WorkOrder"),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("collaborators", "0016_collaboratorbenefit_source_payroll_and_manual_commission"),
        ("budget", "0069_merge_budget_cancellation_responsible"),
        ("workorder", "0046_leftover_courtesy_reason_default"),
    ]

    operations = [
        migrations.RunPython(_backfill_commission_titles, migrations.RunPython.noop),
    ]
