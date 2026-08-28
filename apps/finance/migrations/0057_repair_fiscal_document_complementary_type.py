from django.db import migrations, models

from . import _idempotent


def repair_legacy_text_defaults(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    table = "finance_fiscaldocument"
    if table not in schema_editor.connection.introspection.table_names():
        return

    leftover_columns = ("complementary_type", "fiscal_purpose_type")
    quoted_table = schema_editor.quote_name(table)
    with schema_editor.connection.cursor() as cursor:
        existing = {
            getattr(column, "name", column[0])
            for column in schema_editor.connection.introspection.get_table_description(cursor, table)
        }
        for column_name in leftover_columns:
            if column_name not in existing:
                continue
            quoted_column = schema_editor.quote_name(column_name)
            schema_editor.execute(f"ALTER TABLE {quoted_table} ALTER COLUMN {quoted_column} SET DEFAULT ''")
            schema_editor.execute(f"UPDATE {quoted_table} SET {quoted_column} = '' WHERE {quoted_column} IS NULL")
            schema_editor.execute(f"ALTER TABLE {quoted_table} ALTER COLUMN {quoted_column} SET NOT NULL")


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0056_merge_nf_and_os_backfill"),
    ]

    operations = [
        _idempotent.AddFieldIfMissing(
            model_name="fiscaldocument",
            name="complementary_type",
            field=models.CharField(
                blank=True,
                choices=[("price_quantity", "Preço/quantidade")],
                db_index=True,
                default="",
                max_length=32,
            ),
        ),
        migrations.RunPython(repair_legacy_text_defaults, migrations.RunPython.noop),
    ]
