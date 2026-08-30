from __future__ import annotations

from datetime import date

from django.db import connection
from django.test import TestCase

from apps.accounts.models import Account
from apps.budget.models import Budget, BudgetStatus
from apps.workorder.models import WorkOrder
from apps.workshops.models.workshops import Workshop


class LeftoverCourtesyReasonColumnTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta leftover courtesy")
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina leftover courtesy",
            cnpj="12.345.678/0001-93",
            phone="+5511999999997",
            address="Rua Leftover, 1",
        )

    def test_budget_approve_creates_workorder_when_leftover_courtesy_column_has_no_default(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                ALTER TABLE workorder_workorder
                ADD COLUMN IF NOT EXISTS courtesy_reason_description text NOT NULL DEFAULT ''
                """
            )
            cursor.execute("ALTER TABLE workorder_workorder ALTER COLUMN courtesy_reason_description DROP DEFAULT")

        from apps.workorder.migrations._idempotent import ensure_empty_string_default

        with connection.schema_editor() as schema_editor:
            ensure_empty_string_default(
                schema_editor,
                table="workorder_workorder",
                columns=("courtesy_reason_description",),
            )

        budget = Budget(workshop=self.workshop, entry_date=date(2026, 8, 24), status=BudgetStatus.WAITING_REVIEW)
        budget.save()
        self.assertTrue(budget.approve())

        self.assertTrue(WorkOrder.objects.filter(budget=budget).exists())
