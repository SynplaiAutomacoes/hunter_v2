from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from apps.workshops.models.workshops import Workshop
from apps.workshops.util.default_setup import create_default_workshop_setup


class Command(BaseCommand):
    help = "Aplica o catálogo padrão hardcoded (formas de pagamento, grupos financeiros e perguntas investigativas) em uma ou mais oficinas. Idempotente."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--workshop-id", type=int, help="ID da oficina alvo.")
        parser.add_argument(
            "--all-empty",
            action="store_true",
            help="Aplica em oficinas sem formas de pagamento, grupos financeiros e perguntas investigativas.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria criado sem gravar.")

    def handle(self, *args: object, **options: object) -> None:
        workshop_id = options.get("workshop_id")
        all_empty = bool(options["all_empty"])
        dry_run = bool(options["dry_run"])

        if workshop_id is None and not all_empty:
            raise CommandError("Informe --workshop-id ou --all-empty.")
        if workshop_id is not None and all_empty:
            raise CommandError("Use apenas um de --workshop-id ou --all-empty.")

        workshops = self._resolve_workshops(workshop_id=workshop_id if isinstance(workshop_id, int) else None, all_empty=all_empty)
        if not workshops:
            self.stdout.write(self.style.WARNING("Nenhuma oficina correspondente encontrada."))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("Modo dry-run: nenhuma alteração será persistida."))

        results: list[dict[str, object]] = []
        with transaction.atomic():
            for workshop in workshops:
                summary = create_default_workshop_setup(workshop=workshop)
                payload = {"workshop_id": workshop.id, "workshop_name": workshop.name, **summary}
                results.append(payload)
                self.stdout.write(f"[{workshop.id}] {workshop.name}: pm={summary['payment_methods_created']} fg={summary['financial_groups_created']} iq={summary['investigative_questions_created']}")
            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(json.dumps(results, ensure_ascii=False, sort_keys=True)))

    @staticmethod
    def _resolve_workshops(*, workshop_id: int | None, all_empty: bool) -> list[Workshop]:
        if workshop_id is not None:
            workshop = Workshop.objects.filter(pk=workshop_id).first()
            if workshop is None:
                raise CommandError(f"Oficina com id={workshop_id} não encontrada.")
            return [workshop]

        return list(
            Workshop.objects.annotate(
                payment_methods_count=Count("payment_methods", distinct=True),
                financial_groups_count=Count("financial_groups", distinct=True),
                investigative_questions_count=Count("investigative_questions", distinct=True),
            )
            .filter(
                payment_methods_count=0,
                financial_groups_count=0,
                investigative_questions_count=0,
            )
            .order_by("id")
        )
