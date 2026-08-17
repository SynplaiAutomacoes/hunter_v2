# Restores stock fiscal columns dropped after a staging/homol merge.
#
# django_migrations still records 0016-0019 as applied, but later ghost
# migrations (0015_remove_stockimport_fiscal_snapshot, 0016_fix_merge_staging)
# dropped the columns with RunSQL and did not update Django state. Queries such
# as GET /stock/ then fail with UndefinedColumn: stock_stockimport.fiscal_document_id.
#
# State is left unchanged: the fields are already present in the migration graph.

from django.db import migrations

RESTORE_STOCK_IMPORT_COLUMNS_SQL = """
    ALTER TABLE stock_stockimport
        ADD COLUMN IF NOT EXISTS fiscal_document_id bigint NULL,
        ADD COLUMN IF NOT EXISTS fiscal_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
        ADD COLUMN IF NOT EXISTS fiscal_issued_at timestamptz NULL,
        ADD COLUMN IF NOT EXISTS fiscal_validation_status varchar(16) NOT NULL DEFAULT 'unvalidated',
        ADD COLUMN IF NOT EXISTS fiscal_validated_at timestamptz NULL;
"""

RESTORE_STOCK_MOVEMENT_COLUMNS_SQL = """
    ALTER TABLE stock_stockmovement
        ADD COLUMN IF NOT EXISTS source_import_item_id bigint NULL,
        ADD COLUMN IF NOT EXISTS fiscal_document_id bigint NULL,
        ADD COLUMN IF NOT EXISTS purchase_return_item_id bigint NULL,
        ADD COLUMN IF NOT EXISTS transport_item_id bigint NULL;
"""

RESTORE_INDEXES_SQL = """
    CREATE UNIQUE INDEX IF NOT EXISTS stock_stockimport_fiscal_document_id_key
        ON stock_stockimport (fiscal_document_id);
    CREATE INDEX IF NOT EXISTS stock_stockimport_fiscal_issued_at_idx
        ON stock_stockimport (fiscal_issued_at);
    CREATE INDEX IF NOT EXISTS stock_stockimport_fiscal_validation_status_idx
        ON stock_stockimport (fiscal_validation_status);
    CREATE INDEX IF NOT EXISTS stock_stockmovement_source_import_item_id_idx
        ON stock_stockmovement (source_import_item_id);
    CREATE INDEX IF NOT EXISTS stock_stockmovement_fiscal_document_id_idx
        ON stock_stockmovement (fiscal_document_id);
    CREATE UNIQUE INDEX IF NOT EXISTS stock_stockmovement_purchase_return_item_id_key
        ON stock_stockmovement (purchase_return_item_id);
    CREATE UNIQUE INDEX IF NOT EXISTS stock_stockmovement_transport_item_id_key
        ON stock_stockmovement (transport_item_id);
    CREATE INDEX IF NOT EXISTS stock_stockmovement_reason_idx
        ON stock_stockmovement (reason);
    CREATE UNIQUE INDEX IF NOT EXISTS unique_stock_entry_per_import_item
        ON stock_stockmovement (source_import_item_id)
        WHERE type = 'ENTRADA';
"""

RESTORE_FOREIGN_KEYS_SQL = """
    DO $$
    DECLARE
        rec record;
    BEGIN
        FOR rec IN
            SELECT *
            FROM (
                VALUES
                    ('stock_stockimport', 'fiscal_document_id', 'finance_fiscaldocument'),
                    ('stock_stockmovement', 'source_import_item_id', 'stock_stockimportfiscalitem'),
                    ('stock_stockmovement', 'fiscal_document_id', 'finance_fiscaldocument'),
                    ('stock_stockmovement', 'purchase_return_item_id', 'finance_purchasereturnrequestitem'),
                    ('stock_stockmovement', 'transport_item_id', 'finance_transportrequestitem')
            ) AS t(src_table, src_col, tgt_table)
        LOOP
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class rel ON rel.oid = c.conrelid
                JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = ANY (c.conkey)
                WHERE rel.relname = rec.src_table
                  AND att.attname = rec.src_col
                  AND c.contype = 'f'
            ) THEN
                EXECUTE format(
                    'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES %I(id) DEFERRABLE INITIALLY DEFERRED',
                    rec.src_table,
                    rec.src_table || '_' || rec.src_col || '_fkey',
                    rec.src_col,
                    rec.tgt_table
                );
            END IF;
        END LOOP;
    END $$;
"""

RESTORE_SQL_OPERATIONS = (
    RESTORE_STOCK_IMPORT_COLUMNS_SQL,
    RESTORE_STOCK_MOVEMENT_COLUMNS_SQL,
    RESTORE_INDEXES_SQL,
    RESTORE_FOREIGN_KEYS_SQL,
)


class Migration(migrations.Migration):

    dependencies = [
        ("stock", "0019_stockmovement_transport_item_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=RESTORE_STOCK_IMPORT_COLUMNS_SQL, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(sql=RESTORE_STOCK_MOVEMENT_COLUMNS_SQL, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(sql=RESTORE_INDEXES_SQL, reverse_sql=migrations.RunSQL.noop),
        migrations.RunSQL(sql=RESTORE_FOREIGN_KEYS_SQL, reverse_sql=migrations.RunSQL.noop),
    ]
