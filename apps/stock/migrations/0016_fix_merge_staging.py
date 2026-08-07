# Generated manually on 2026-08-04

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("stock", "0015_remove_stockimport_fiscal_snapshot"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE stock_stockmovement
                DROP CONSTRAINT IF EXISTS unique_stock_entry_per_import_item;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        migrations.RunSQL(
            sql="""
                ALTER TABLE stock_stockimport
                DROP CONSTRAINT IF EXISTS unique_stock_import_access_key_per_workshop;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        migrations.RunSQL(
            sql="""
                ALTER TABLE stock_stockmovement
                DROP COLUMN IF EXISTS source_import_item_id,
                DROP COLUMN IF EXISTS fiscal_document_id,
                DROP COLUMN IF EXISTS purchase_return_item_id,
                DROP COLUMN IF EXISTS transport_item_id,
                DROP COLUMN IF EXISTS reason;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        migrations.RunSQL(
            sql="""
                ALTER TABLE stock_stockimport
                DROP COLUMN IF EXISTS fiscal_document_id,
                DROP COLUMN IF EXISTS fiscal_issued_at,
                DROP COLUMN IF EXISTS fiscal_validation_status,
                DROP COLUMN IF EXISTS fiscal_validated_at;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        migrations.RunSQL(
            sql="""
                ALTER TABLE stock_stockproduct
                ALTER COLUMN current_quantity TYPE integer
                USING current_quantity::integer;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        migrations.RunSQL(
            sql="""
                ALTER TABLE stock_stockmovement
                ALTER COLUMN quantity TYPE integer
                USING quantity::integer;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
