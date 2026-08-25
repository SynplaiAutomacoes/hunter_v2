"""Idempotent migration operations for historical fiscal schemas."""

from __future__ import annotations

from typing import Any

from django.db import migrations


def _table_names(schema_editor: Any) -> set[str]:
    return set(schema_editor.connection.introspection.table_names())


def _column_names(schema_editor: Any, table: str) -> set[str]:
    with schema_editor.connection.cursor() as cursor:
        description = schema_editor.connection.introspection.get_table_description(cursor, table)
    return {getattr(column, "name", column[0]) for column in description}


def _index_exists(schema_editor: Any, index_name: str) -> bool:
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() AND indexname = %s",
            [index_name],
        )
        return cursor.fetchone() is not None


def _constraint_exists(schema_editor: Any, constraint_name: str) -> bool:
    if _index_exists(schema_editor, constraint_name):
        return True
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM pg_constraint constraint
            JOIN pg_namespace namespace ON namespace.oid = constraint.connamespace
            WHERE namespace.nspname = current_schema() AND constraint.conname = %s
            """,
            [constraint_name],
        )
        return cursor.fetchone() is not None


class CreateModelIfMissing(migrations.CreateModel):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.name)
        if model._meta.db_table not in _table_names(schema_editor):
            super().database_forwards(app_label, schema_editor, from_state, to_state)


class AddFieldIfMissing(migrations.AddField):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        model = to_state.apps.get_model(app_label, self.model_name)
        table = model._meta.db_table
        if table in _table_names(schema_editor) and model._meta.get_field(self.name).column not in _column_names(schema_editor, table):
            super().database_forwards(app_label, schema_editor, from_state, to_state)


class AddIndexIfMissing(migrations.AddIndex):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if not _index_exists(schema_editor, self.index.name):
            super().database_forwards(app_label, schema_editor, from_state, to_state)


class AddConstraintIfMissing(migrations.AddConstraint):
    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if not _constraint_exists(schema_editor, self.constraint.name):
            super().database_forwards(app_label, schema_editor, from_state, to_state)
