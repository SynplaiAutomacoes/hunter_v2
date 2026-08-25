"""Idempotent migration ops for DBs that already have historical fiscal tables."""

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


def _index_exists(schema_editor: Any, index_name: str) -> bool:
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND indexname = %s
            """,
            [index_name],
        )
        return cursor.fetchone() is not None


def _constraint_exists(schema_editor: Any, constraint_name: str) -> bool:
    """Partial unique constraints may exist only as indexes, not pg_constraint rows."""
    if _index_exists(schema_editor, constraint_name):
        return True
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM pg_constraint c
            JOIN pg_namespace n ON n.oid = c.connamespace
            WHERE n.nspname = current_schema()
              AND c.conname = %s
            """,
            [constraint_name],
        )
        return cursor.fetchone() is not None


class CreateModelIfMissing(migrations.CreateModel):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.name)
        if model._meta.db_table in _table_names(schema_editor):
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        model = from_state.apps.get_model(app_label, self.name)
        if model._meta.db_table not in _table_names(schema_editor):
            return
        super().database_backwards(app_label, schema_editor, from_state, to_state)


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


class AddIndexIfMissing(migrations.AddIndex):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if _index_exists(schema_editor, self.index.name):
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if not _index_exists(schema_editor, self.index.name):
            return
        super().database_backwards(app_label, schema_editor, from_state, to_state)


class AddConstraintIfMissing(migrations.AddConstraint):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if _constraint_exists(schema_editor, self.constraint.name):
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if not _constraint_exists(schema_editor, self.constraint.name):
            return
        super().database_backwards(app_label, schema_editor, from_state, to_state)
