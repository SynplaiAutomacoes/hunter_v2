from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.collaborators.services import recalculate_historical_commissions
from apps.workshops.models.workshops import Workshop


class Command(BaseCommand):
    help = "Recalcula comissoes historicas com base no valor total de servicos da O.S."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--workshop-id", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options) -> None:
        workshop_id = options.get("workshop_id")
        dry_run = bool(options.get("dry_run"))
        workshop = None
        if workshop_id is not None:
            workshop = Workshop.objects.filter(pk=workshop_id).first()
            if workshop is None:
                self.stderr.write(self.style.ERROR("Oficina não encontrada."))
                return

        result = recalculate_historical_commissions(workshop=workshop, dry_run=dry_run)
        scope = f"oficina {workshop.pk}" if workshop is not None else "todas as oficinas"
        mode = "simulação" if dry_run else "aplicação"
        self.stdout.write(self.style.SUCCESS(f"Recálculo concluído ({mode}) em {scope}: {result['updated_entries']} comissões e {result['updated_payrolls']} folhas atualizadas."))
