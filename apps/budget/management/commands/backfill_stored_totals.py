from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.budget.models import Budget
from apps.workorder.models import WorkOrder


class Command(BaseCommand):
    """Backfill denormalized list/dashboard totals after wave2 stored_* fields.

    Run once after deploying stored_total_amount migrations, e.g.:

        uv run python manage.py backfill_stored_totals --batch-size 100
    """

    help = "Recalcula Budget.stored_total_amount e WorkOrder stored totals em batches."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--budgets-only", action="store_true")
        parser.add_argument("--workorders-only", action="store_true")

    def handle(self, *args, **options) -> None:
        batch_size = max(int(options.get("batch_size") or 100), 1)
        budgets_only = bool(options.get("budgets_only"))
        workorders_only = bool(options.get("workorders_only"))

        budget_count = 0
        workorder_count = 0

        if not workorders_only:
            budget_count = self._backfill_budgets(batch_size=batch_size)
        if not budgets_only:
            workorder_count = self._backfill_workorders(batch_size=batch_size)

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill concluído. Budgets: {budget_count}. WorkOrders: {workorder_count}."
            )
        )

    def _backfill_budgets(self, *, batch_size: int) -> int:
        updated = 0
        last_pk = 0
        while True:
            batch = list(Budget.objects.filter(pk__gt=last_pk).order_by("pk")[:batch_size])
            if not batch:
                break
            for budget in batch:
                budget.refresh_stored_total_amount()
                updated += 1
            last_pk = batch[-1].pk
            self.stdout.write(f"Budgets processados até pk={last_pk} ({updated})")
        return updated

    def _backfill_workorders(self, *, batch_size: int) -> int:
        updated = 0
        last_pk = 0
        while True:
            batch = list(
                WorkOrder.objects.filter(pk__gt=last_pk)
                .select_related("budget")
                .prefetch_related("payments", "items")
                .order_by("pk")[:batch_size]
            )
            if not batch:
                break
            for workorder in batch:
                workorder.refresh_stored_amounts()
                updated += 1
            last_pk = batch[-1].pk
            self.stdout.write(f"WorkOrders processados até pk={last_pk} ({updated})")
        return updated
