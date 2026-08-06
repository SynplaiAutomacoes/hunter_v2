from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.core.infrastructure.services.dashboard_snapshot_service import freeze_due_snapshots


class Command(BaseCommand):
    help = (
        "Congela snapshots do dashboard para meses já fechados (após o último dia às 23:59 "
        "America/Sao_Paulo) que ainda não tenham registro. Seguro para rodar no dia 1 do mês "
        "ou via cron após o cutoff. Snapshots existentes não são sobrescritos."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--workshop-id",
            type=int,
            default=None,
            help="Limita o freeze a uma oficina específica.",
        )

    def handle(self, *args: object, **options: object) -> None:
        workshop_id = options.get("workshop_id")
        created = freeze_due_snapshots(workshop_id=workshop_id if isinstance(workshop_id, int) else None)
        self.stdout.write(self.style.SUCCESS(f"Snapshots criados: {created}"))
