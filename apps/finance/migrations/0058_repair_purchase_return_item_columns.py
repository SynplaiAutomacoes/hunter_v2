from django.db import migrations

from . import _idempotent


def _nullable_columns(schema_editor, table: str) -> dict[str, bool]:
    if schema_editor.connection.vendor != "postgresql":
        return {}
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name, is_nullable
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
            """,
            [table],
        )
        return {name: nullable == "YES" for name, nullable in cursor.fetchall()}


def sync_model_columns(apps, schema_editor, *, app_label: str, model_name: str) -> None:
    model = apps.get_model(app_label, model_name)
    table = model._meta.db_table
    if table not in schema_editor.connection.introspection.table_names():
        return

    existing = _idempotent._column_names(schema_editor, table)
    for field in model._meta.local_concrete_fields:
        if field.column in existing:
            continue
        schema_editor.add_field(model, field)

    if schema_editor.connection.vendor != "postgresql":
        return

    existing = _idempotent._column_names(schema_editor, table)
    nullable = _nullable_columns(schema_editor, table)
    quoted_table = schema_editor.quote_name(table)
    for field in model._meta.local_concrete_fields:
        if field.column not in existing or not field.null:
            continue
        if nullable.get(field.column, True):
            continue
        schema_editor.execute(f"ALTER TABLE {quoted_table} ALTER COLUMN {schema_editor.quote_name(field.column)} DROP NOT NULL")


def repair_purchase_return_schema(apps, schema_editor):
    sync_model_columns(apps, schema_editor, app_label="finance", model_name="PurchaseReturnRequest")
    sync_model_columns(apps, schema_editor, app_label="finance", model_name="PurchaseReturnRequestItem")


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0057_repair_fiscal_document_complementary_type"),
    ]

    operations = [
        migrations.RunPython(repair_purchase_return_schema, migrations.RunPython.noop),
    ]
