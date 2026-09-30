# Generated manually to drop orphan columns on finance_fiscaldocumentevent
# left over from a reverted "NF-e cancellation events" branch.

from django.db import migrations

from apps.finance.migrations import _idempotent

ORPHAN_COLUMNS = ("event_code", "event_payload_type", "related_event_id")


def drop_orphan_fiscal_event_columns(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    table = "finance_fiscaldocumentevent"
    if table not in schema_editor.connection.introspection.table_names():
        return

    existing = _idempotent._column_names(schema_editor, table)
    quoted_table = schema_editor.quote_name(table)
    for column_name in ORPHAN_COLUMNS:
        if column_name not in existing:
            continue
        schema_editor.execute(f"ALTER TABLE {quoted_table} DROP COLUMN {schema_editor.quote_name(column_name)}")


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0068_purchase_return_supplier_ie"),
    ]

    operations = [
        migrations.RunPython(drop_orphan_fiscal_event_columns, migrations.RunPython.noop),
    ]
