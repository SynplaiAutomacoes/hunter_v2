# Generated manually on 2026-08-04

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("stock", "0014_stockimport_xml_file_key_index"),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE "stock_stockimport" DROP COLUMN IF EXISTS "fiscal_snapshot";',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
