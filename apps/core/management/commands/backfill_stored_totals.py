from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.core.infrastructure.services.stored_totals import backfill_stored_totals


class Command(BaseCommand):
    help = (
        "Reconstrói os totais denormalizados de orçamentos e ordens de serviço de forma idempotente. "
        "Inclui valor operacional de garantia/cortesia para listagens."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--batch-size", type=int, default=250)
        parser.add_argument("--workshop-id", type=int)
        parser.add_argument(
            "--budget-types",
            type=str,
            help="Lista separada por vírgula (ex.: warranty,courtesy). Sem filtro processa todos.",
        )

    def handle(self, *args: object, **options: object) -> None:
        batch_size = int(options["batch_size"])
        if batch_size <= 0:
            raise CommandError("--batch-size deve ser maior que zero.")

        budget_types_raw = options.get("budget_types")
        budget_types: frozenset[str] | None = None
        if budget_types_raw:
            budget_types = frozenset(part.strip() for part in str(budget_types_raw).split(",") if part.strip())
            if not budget_types:
                raise CommandError("--budget-types não pode ser vazio.")

        result = backfill_stored_totals(
            batch_size=batch_size,
            workshop_id=options.get("workshop_id"),
            budget_types=budget_types,
        )
        payload = {
            "budgets_scanned": result.budgets_scanned,
            "budgets_updated": result.budgets_updated,
            "workorders_scanned": result.workorders_scanned,
            "workorders_updated": result.workorders_updated,
        }
        self.stdout.write(self.style.SUCCESS(json.dumps(payload, sort_keys=True)))
