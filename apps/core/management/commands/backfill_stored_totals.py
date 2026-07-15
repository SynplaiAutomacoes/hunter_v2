from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.core.infrastructure.services.stored_totals import backfill_stored_totals


class Command(BaseCommand):
    help = "Reconstrói os totais denormalizados de orçamentos e ordens de serviço de forma idempotente."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--batch-size", type=int, default=250)
        parser.add_argument("--workshop-id", type=int)

    def handle(self, *args: object, **options: object) -> None:
        batch_size = int(options["batch_size"])
        if batch_size <= 0:
            raise CommandError("--batch-size deve ser maior que zero.")

        result = backfill_stored_totals(
            batch_size=batch_size,
            workshop_id=options.get("workshop_id"),
        )
        payload = {
            "budgets_scanned": result.budgets_scanned,
            "budgets_updated": result.budgets_updated,
            "workorders_scanned": result.workorders_scanned,
            "workorders_updated": result.workorders_updated,
        }
        self.stdout.write(self.style.SUCCESS(json.dumps(payload, sort_keys=True)))
