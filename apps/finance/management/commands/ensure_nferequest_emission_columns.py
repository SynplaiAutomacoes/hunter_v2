from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection


RESTORE_NFEREQUEST_EMISSION_COLUMNS_SQL = """
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
"""


def ensure_nferequest_emission_columns() -> None:
    """Idempotently restore columns dropped by finance.0046_revert_staging_merge.

    Staging/homol models still select these fields. Running this before migrate avoids
    ProgrammingError without introducing a second migration leaf alongside 0091.
    """
    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = 'finance_nferequest'
            """
        )
        if cursor.fetchone() is None:
            return

        cursor.execute(RESTORE_NFEREQUEST_EMISSION_COLUMNS_SQL)


class Command(BaseCommand):
    help = "Garante colunas emission_origin/freight_mode/transport_snapshot em finance_nferequest."

    def handle(self, *args, **options) -> None:
        ensure_nferequest_emission_columns()
        self.stdout.write(self.style.SUCCESS("Colunas de emissão NF-e verificadas/restauradas em finance_nferequest."))
