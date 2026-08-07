# Generated manually on 2026-08-04

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0045_financialmovement_payroll_benefit"),
    ]

    operations = [

        migrations.RunSQL(
            sql="""
                ALTER TABLE finance_taxclassnfe
                DROP COLUMN IF EXISTS ibs_cbs_enabled,
                DROP COLUMN IF EXISTS ibs_cbs_situacao_tributaria,
                DROP COLUMN IF EXISTS ibs_cbs_classificacao_tributaria,
                DROP COLUMN IF EXISTS ibs_cbs_situacao_tributaria_regular,
                DROP COLUMN IF EXISTS ibs_cbs_classificacao_tributaria_regular,
                DROP COLUMN IF EXISTS ibs_cbs_details,
                DROP COLUMN IF EXISTS ibs_cbs_configured_at,
                DROP COLUMN IF EXISTS ibs_cbs_configured_by_id;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        migrations.RunSQL(
            sql="""
                ALTER TABLE finance_webmaniacompany
                DROP COLUMN IF EXISTS nfce_enabled,
                DROP COLUMN IF EXISTS credit_debit_basis_enabled,
                DROP COLUMN IF EXISTS credit_debit_basis_enabled_by_id,
                DROP COLUMN IF EXISTS credit_debit_basis_enabled_at,
                DROP COLUMN IF EXISTS nfe_debit_emission_enabled,
                DROP COLUMN IF EXISTS nfe_debit_emission_enabled_by_id,
                DROP COLUMN IF EXISTS nfe_debit_emission_enabled_at,
                DROP COLUMN IF EXISTS nfse_legacy_compatibility_enabled,
                DROP COLUMN IF EXISTS nfse_substitution_preview_enabled,
                DROP COLUMN IF EXISTS nfse_manual_emission_preview_enabled,
                DROP COLUMN IF EXISTS nfse_manual_emission_enabled,
                DROP COLUMN IF EXISTS nfse_received_import_enabled,
                DROP COLUMN IF EXISTS nfse_received_consultation_enabled,
                DROP COLUMN IF EXISTS nfse_external_xml_inbox_enabled;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        migrations.RunSQL(
            sql="""
                ALTER TABLE finance_nferequest
                DROP COLUMN IF EXISTS manual_recipient,
                DROP COLUMN IF EXISTS emission_origin,
                DROP COLUMN IF EXISTS freight_mode,
                DROP COLUMN IF EXISTS transport_snapshot;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        migrations.RunSQL(
            sql="""
                ALTER TABLE finance_nfseitem
                DROP COLUMN IF EXISTS remote_updated_at,
                DROP COLUMN IF EXISTS last_update_source;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        migrations.RunSQL(
            sql="""
                ALTER TABLE finance_nfsebatch
                DROP COLUMN IF EXISTS remote_updated_at,
                DROP COLUMN IF EXISTS last_reconciled_at,
                DROP COLUMN IF EXISTS last_update_source;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        migrations.RunSQL(
            sql="""
                ALTER TABLE finance_nferequest
                DROP CONSTRAINT IF EXISTS nfe_request_origin_matches_workorder;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        migrations.RunSQL(
            sql="""
                DROP INDEX IF EXISTS tax_class_nfe_workshop_ibs_enabled_idx;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
