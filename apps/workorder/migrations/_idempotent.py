"""Idempotent migration ops for leftover columns from incomplete OS reverts."""

from __future__ import annotations

from typing import Any

from django.db import migrations


def _table_names(schema_editor: Any) -> set[str]:
    return set(schema_editor.connection.introspection.table_names())


def _column_names(schema_editor: Any, table: str) -> set[str]:
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table)
    return {getattr(col, "name", col[0]) for col in description}


def ensure_empty_string_default(schema_editor: Any, *, table: str, columns: tuple[str, ...]) -> None:
    """Leftover NOT NULL text columns (reverted from Django, still in Postgres) break INSERT."""
    if table not in _table_names(schema_editor):
        return
    existing = _column_names(schema_editor, table)
    quote = schema_editor.quote_name
    with schema_editor.connection.cursor() as cursor:
        for column in columns:
            if column not in existing:
                continue
            quoted_table = quote(table)
            quoted_column = quote(column)
            cursor.execute(f"UPDATE {quoted_table} SET {quoted_column} = '' WHERE {quoted_column} IS NULL")
            cursor.execute(f"ALTER TABLE {quoted_table} ALTER COLUMN {quoted_column} SET DEFAULT ''")
            cursor.execute(f"ALTER TABLE {quoted_table} ALTER COLUMN {quoted_column} SET NOT NULL")


class AddFieldIfMissing(migrations.AddField):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        table = model._meta.db_table
        if table not in _table_names(schema_editor):
            return
        field = model._meta.get_field(self.name)
        column = field.column
        if column in _column_names(schema_editor, table):
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        model = from_state.apps.get_model(app_label, self.model_name)
        table = model._meta.db_table
        if table not in _table_names(schema_editor):
            return
        field = model._meta.get_field(self.name)
        column = field.column
        if column not in _column_names(schema_editor, table):
            return
        super().database_backwards(app_label, schema_editor, from_state, to_state)
