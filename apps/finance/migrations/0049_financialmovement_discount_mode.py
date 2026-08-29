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
                    sql="""
                        ALTER TABLE finance_financialmovement
                            ADD COLUMN IF NOT EXISTS discount_mode varchar(20) NOT NULL DEFAULT 'NONE';
                        ALTER TABLE finance_financialmovement
                            ALTER COLUMN discount_mode SET DEFAULT 'NONE';

                        DO $$
                        BEGIN
                            IF EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name = 'finance_financialmovement'
                                  AND column_name = 'entry_date'
                            ) THEN
                                ALTER TABLE finance_financialmovement
                                    ALTER COLUMN entry_date SET DEFAULT CURRENT_DATE;
                            END IF;

                            IF EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name = 'finance_financialmovement'
                                  AND column_name = 'discount_percentage'
                            ) THEN
                                ALTER TABLE finance_financialmovement
                                    ALTER COLUMN discount_percentage SET DEFAULT 0;
                            END IF;

                            IF EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name = 'finance_financialmovement'
                                  AND column_name = 'discount_value'
                            ) THEN
                                ALTER TABLE finance_financialmovement
                                    ALTER COLUMN discount_value SET DEFAULT 0;
                            END IF;

                            IF EXISTS (
                                SELECT 1 FROM information_schema.columns
                                WHERE table_name = 'finance_financialmovement'
                                  AND column_name = 'discount_value_currency'
                            ) THEN
                                ALTER TABLE finance_financialmovement
                                    ALTER COLUMN discount_value_currency SET DEFAULT 'BRL';
                            END IF;
                        END $$;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[],
        ),
    ]
