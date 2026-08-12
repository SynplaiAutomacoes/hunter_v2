# Restores fiscal columns dropped by 0046_revert_staging_merge.
#
# That migration used RunSQL DROP COLUMN IF EXISTS and does not update Django
# state. After it was merged into staging/homol, Django still believed the
# fields existed (AddField migrations in the fiscal graph), but Postgres no
# longer had the columns. Queries such as Workshop.pdf_name then failed with
# UndefinedColumn: finance_webmaniacompany.nfce_enabled.
#
# State is left unchanged: the fields are already present in the migration graph.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0092_merge_20260810_1632"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE finance_taxclassnfe
                    ADD COLUMN IF NOT EXISTS ibs_cbs_enabled boolean NOT NULL DEFAULT false,
                    ADD COLUMN IF NOT EXISTS ibs_cbs_situacao_tributaria varchar(3) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS ibs_cbs_classificacao_tributaria varchar(6) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS ibs_cbs_situacao_tributaria_regular varchar(3) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS ibs_cbs_classificacao_tributaria_regular varchar(6) NOT NULL DEFAULT '',
                    ADD COLUMN IF NOT EXISTS ibs_cbs_details jsonb NOT NULL DEFAULT '{}'::jsonb,
                    ADD COLUMN IF NOT EXISTS ibs_cbs_configured_at timestamptz NULL,
                    ADD COLUMN IF NOT EXISTS ibs_cbs_configured_by_id bigint NULL;

                CREATE INDEX IF NOT EXISTS finance_tax_worksho_1b48f9_idx
                    ON finance_taxclassnfe (workshop_id, ibs_cbs_enabled);
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE finance_webmaniacompany
                    ADD COLUMN IF NOT EXISTS nfce_enabled boolean NOT NULL DEFAULT false,
                    ADD COLUMN IF NOT EXISTS credit_debit_basis_enabled boolean NOT NULL DEFAULT false,
                    ADD COLUMN IF NOT EXISTS credit_debit_basis_enabled_by_id bigint NULL,
                    ADD COLUMN IF NOT EXISTS credit_debit_basis_enabled_at timestamptz NULL,
                    ADD COLUMN IF NOT EXISTS nfe_debit_emission_enabled boolean NOT NULL DEFAULT false,
                    ADD COLUMN IF NOT EXISTS nfe_debit_emission_enabled_by_id bigint NULL,
                    ADD COLUMN IF NOT EXISTS nfe_debit_emission_enabled_at timestamptz NULL,
                    ADD COLUMN IF NOT EXISTS nfse_legacy_compatibility_enabled boolean NOT NULL DEFAULT true,
                    ADD COLUMN IF NOT EXISTS nfse_substitution_preview_enabled boolean NOT NULL DEFAULT false,
                    ADD COLUMN IF NOT EXISTS nfse_manual_emission_preview_enabled boolean NOT NULL DEFAULT false,
                    ADD COLUMN IF NOT EXISTS nfse_manual_emission_enabled boolean NOT NULL DEFAULT false,
                    ADD COLUMN IF NOT EXISTS nfse_received_import_enabled boolean NOT NULL DEFAULT false,
                    ADD COLUMN IF NOT EXISTS nfse_received_consultation_enabled boolean NOT NULL DEFAULT false,
                    ADD COLUMN IF NOT EXISTS nfse_external_xml_inbox_enabled boolean NOT NULL DEFAULT false;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE finance_nferequest
                    ADD COLUMN IF NOT EXISTS manual_recipient_id bigint NULL,
                    ADD COLUMN IF NOT EXISTS emission_origin varchar(16) NOT NULL DEFAULT 'work_order',
                    ADD COLUMN IF NOT EXISTS freight_mode smallint NOT NULL DEFAULT 9,
                    ADD COLUMN IF NOT EXISTS transport_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb;

                CREATE INDEX IF NOT EXISTS finance_nferequest_emission_origin_idx
                    ON finance_nferequest (emission_origin);
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE finance_nfseitem
                    ADD COLUMN IF NOT EXISTS remote_updated_at timestamptz NULL,
                    ADD COLUMN IF NOT EXISTS last_update_source varchar(20) NOT NULL DEFAULT '';

                CREATE INDEX IF NOT EXISTS finance_nfseitem_remote_updated_at_idx
                    ON finance_nfseitem (remote_updated_at);
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
                ALTER TABLE finance_nfsebatch
                    ADD COLUMN IF NOT EXISTS remote_updated_at timestamptz NULL,
                    ADD COLUMN IF NOT EXISTS last_reconciled_at timestamptz NULL,
                    ADD COLUMN IF NOT EXISTS last_update_source varchar(20) NOT NULL DEFAULT '';

                CREATE INDEX IF NOT EXISTS finance_nfsebatch_remote_updated_at_idx
                    ON finance_nfsebatch (remote_updated_at);
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
                DO $$
                DECLARE
                    rec record;
                BEGIN
                    FOR rec IN
                        SELECT *
                        FROM (
                            VALUES
                                ('finance_taxclassnfe', 'ibs_cbs_configured_by_id', 'accounts_user', 'SET NULL'),
                                ('finance_webmaniacompany', 'credit_debit_basis_enabled_by_id', 'accounts_user', 'SET NULL'),
                                ('finance_webmaniacompany', 'nfe_debit_emission_enabled_by_id', 'accounts_user', 'SET NULL'),
                                ('finance_nferequest', 'manual_recipient_id', 'customer_customer', 'NO ACTION')
                        ) AS t(src_table, src_col, tgt_table, on_delete)
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
                                'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES %I(id) ON DELETE %s',
                                rec.src_table,
                                rec.src_table || '_' || rec.src_col || '_fkey',
                                rec.src_col,
                                rec.tgt_table,
                                rec.on_delete
                            );
                        END IF;
                    END LOOP;
                END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'nfe_request_origin_matches_workorder'
                    ) AND NOT EXISTS (
                        SELECT 1
                        FROM finance_nferequest
                        WHERE NOT (
                            (emission_origin = 'work_order' AND workorder_id IS NOT NULL AND manual_recipient_id IS NULL)
                            OR (emission_origin = 'manual' AND workorder_id IS NULL AND manual_recipient_id IS NOT NULL)
                        )
                    ) THEN
                        ALTER TABLE finance_nferequest
                            ADD CONSTRAINT nfe_request_origin_matches_workorder
                            CHECK (
                                (emission_origin = 'work_order' AND workorder_id IS NOT NULL AND manual_recipient_id IS NULL)
                                OR (emission_origin = 'manual' AND workorder_id IS NULL AND manual_recipient_id IS NOT NULL)
                            );
                    END IF;
                END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
