# Generated manually to restore columns dropped by 0046_revert_staging_merge raw SQL.
#
# Staging/homol models still select emission_origin/freight_mode/transport_snapshot.
# Main/hotfix models do not use these fields, but keeping the columns makes promotion
# to staging/homol/prod safe without ProgrammingError on workorder pages.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0046_revert_staging_merge"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE finance_nferequest
                    ADD COLUMN IF NOT EXISTS emission_origin varchar(16) DEFAULT 'work_order',
                    ADD COLUMN IF NOT EXISTS freight_mode smallint DEFAULT 9,
                    ADD COLUMN IF NOT EXISTS transport_snapshot jsonb DEFAULT '{}'::jsonb;

                UPDATE finance_nferequest SET emission_origin = 'work_order' WHERE emission_origin IS NULL;
                UPDATE finance_nferequest SET freight_mode = 9 WHERE freight_mode IS NULL;
                UPDATE finance_nferequest SET transport_snapshot = '{}'::jsonb WHERE transport_snapshot IS NULL;

                ALTER TABLE finance_nferequest
                    ALTER COLUMN emission_origin SET DEFAULT 'work_order',
                    ALTER COLUMN emission_origin SET NOT NULL,
                    ALTER COLUMN freight_mode SET DEFAULT 9,
                    ALTER COLUMN freight_mode SET NOT NULL,
                    ALTER COLUMN transport_snapshot SET DEFAULT '{}'::jsonb,
                    ALTER COLUMN transport_snapshot SET NOT NULL;

                CREATE INDEX IF NOT EXISTS finance_nferequest_emission_origin_idx
                    ON finance_nferequest (emission_origin);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS finance_nferequest_emission_origin_idx;
                ALTER TABLE finance_nferequest
                    DROP COLUMN IF EXISTS emission_origin,
                    DROP COLUMN IF EXISTS freight_mode,
                    DROP COLUMN IF EXISTS transport_snapshot;
            """,
        ),
    ]
