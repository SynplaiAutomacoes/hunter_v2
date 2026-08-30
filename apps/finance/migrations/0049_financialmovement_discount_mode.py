# Historical migration retained because it has already been applied to the local database.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0048_nfserequest_codigo_nbs"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE finance_financialmovement ADD COLUMN IF NOT EXISTS discount_mode varchar(20) NOT NULL DEFAULT '';",
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[],
        ),
    ]
