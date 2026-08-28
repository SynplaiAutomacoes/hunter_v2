from django.db import migrations


def add_missing_kind_column(apps, schema_editor):
    table = "finance_purchasereturnrequestitem"
    if table not in schema_editor.connection.introspection.table_names():
        return

    with schema_editor.connection.cursor() as cursor:
        columns = {
            getattr(column, "name", column[0])
            for column in schema_editor.connection.introspection.get_table_description(cursor, table)
        }
    if "kind" in columns:
        return

    quoted_table = schema_editor.quote_name(table)
    quoted_column = schema_editor.quote_name("kind")
    schema_editor.execute(
        f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_column} varchar(12) NOT NULL DEFAULT 'stock'"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0054_purchase_return_stock_workflow"),
    ]

    operations = [
        migrations.RunPython(add_missing_kind_column, migrations.RunPython.noop),
    ]
