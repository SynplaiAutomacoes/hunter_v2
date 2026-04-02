from django.db import migrations


def ensure_budget_collaborator_column(apps, schema_editor):
    budget_model = apps.get_model("budget", "Budget")
    collaborator_field = budget_model._meta.get_field("collaborator")
    table_name = budget_model._meta.db_table
    column_name = collaborator_field.column

    with schema_editor.connection.cursor() as cursor:
        existing_columns = {column.name for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)}

    if column_name in existing_columns:
        return

    schema_editor.add_field(budget_model, collaborator_field)


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0031_merge_20260330_1905"),
        ("collaborators", "0006_workshopcollaborator_timestamps"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(ensure_budget_collaborator_column, reverse_code=migrations.RunPython.noop),
            ],
            state_operations=[],
        ),
    ]
