from __future__ import annotations

import importlib

from django.db import connection
from django.db.utils import ProgrammingError
from django.test import TransactionTestCase

from apps.stock.models import StockImport, StockMovement

_restore_migration = importlib.import_module("apps.stock.migrations.0020_restore_columns_dropped_by_staging_revert")
RESTORE_SQL_OPERATIONS = _restore_migration.RESTORE_SQL_OPERATIONS


def _apply_restore_sql() -> None:
    with connection.cursor() as cursor:
        for sql in RESTORE_SQL_OPERATIONS:
            cursor.execute(sql)


class RestoreStockFiscalColumnsTests(TransactionTestCase):
    def test_restore_sql_recreates_dropped_fiscal_document_id(self) -> None:
        try:
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE stock_stockimport DROP COLUMN IF EXISTS fiscal_document_id")

            with self.assertRaises(ProgrammingError):
                list(StockImport.objects.all()[:1])

            _apply_restore_sql()

            list(StockImport.objects.all()[:1])
            list(StockMovement.objects.all()[:1])
        finally:
            _apply_restore_sql()

    def test_restore_sql_is_idempotent(self) -> None:
        _apply_restore_sql()
        _apply_restore_sql()

        list(StockImport.objects.all()[:1])
        list(StockMovement.objects.all()[:1])
