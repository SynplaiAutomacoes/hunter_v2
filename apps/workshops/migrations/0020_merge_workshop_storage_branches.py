from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("workshops", "0018_migrate_workshop_storage_to_s3"),
        ("workshops", "0019_reconcile_workshop_file_columns"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            ALTER TABLE workshops_workshop
            DROP COLUMN IF EXISTS logo,
            DROP COLUMN IF EXISTS logo_mongo_file_id,
            DROP COLUMN IF EXISTS pfx_certificate,
            DROP COLUMN IF EXISTS certificate_mongo_file_id;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
