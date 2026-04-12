from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("workshops", "0017_workshop_certificate_content_type_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            ALTER TABLE workshops_workshop
            ADD COLUMN IF NOT EXISTS logo varchar(100) NULL,
            ADD COLUMN IF NOT EXISTS logo_mongo_file_id varchar(64) NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS pfx_certificate varchar(100) NULL,
            ADD COLUMN IF NOT EXISTS certificate_mongo_file_id varchar(64) NOT NULL DEFAULT '';
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
