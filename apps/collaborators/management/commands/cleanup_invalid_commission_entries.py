from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.collaborators.models import CollaboratorCommissionEntry
from apps.workshops.models.workshops import Workshop


class Command(BaseCommand):
    help = "Lista e remove comissoes vinculadas a O.S. de cortesia/garantia."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--workshop-id", type=int, default=None)
        parser.add_argument("--entry-id", type=int, action="append", dest="entry_ids", default=[])
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options) -> None:
        workshop_id = options.get("workshop_id")
        entry_ids: list[int] = list(dict.fromkeys(options.get("entry_ids") or []))
        dry_run = bool(options.get("dry_run"))

        workshop = None
        if workshop_id is not None:
            workshop = Workshop.objects.filter(pk=workshop_id).first()
            if workshop is None:
                raise CommandError("Oficina nao encontrada.")

        queryset = CollaboratorCommissionEntry.objects.select_related("workorder", "collaborator", "workshop", "workorder__budget")
        if workshop is not None:
            queryset = queryset.filter(workshop=workshop)
        queryset = queryset.filter(Q(workorder__budget_type__in=["warranty", "courtesy"]) | Q(workorder__budget__budget_type__in=["warranty", "courtesy"])).order_by("id")

        if entry_ids:
            queryset = queryset.filter(pk__in=entry_ids)

        entries = list(queryset)
        if not entries:
            self.stdout.write(self.style.WARNING("Nenhuma comissao invalida encontrada."))
            return

        if entry_ids:
            found_ids = {entry.pk for entry in entries}
            missing_ids = [entry_id for entry_id in entry_ids if entry_id not in found_ids]
            if missing_ids:
                raise CommandError(f"Os ids informados nao sao invalidos ou nao foram encontrados: {missing_ids}")

        self.stdout.write(f"Total encontrado: {len(entries)}")
        for entry in entries:
            budget_type = getattr(getattr(entry.workorder, "budget", None), "budget_type", "") or entry.workorder.budget_type
            self.stdout.write(f"- id={entry.pk} oficina={entry.workshop_id} os={entry.workorder_id} colaborador={entry.collaborator_id} tipo={budget_type} status={entry.status} valor={entry.commission_amount}")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("[DRY-RUN] Nenhum registro foi apagado."))
            return

        deleted_count, _ = queryset.delete()
        self.stdout.write(self.style.SUCCESS(f"{deleted_count} comissao(oes) invalida(s) removida(s)."))
