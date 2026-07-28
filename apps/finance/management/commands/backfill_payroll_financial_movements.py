from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.collaborators.models import CollaboratorPayroll
from apps.collaborators.services import sync_collaborator_payroll
from apps.workshops.models.workshops import Workshop


class Command(BaseCommand):
    help = "Cria movimentacoes financeiras ausentes para folhas de pagamento ja existentes."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--workshop-id", type=int, default=None)
        parser.add_argument("--payroll-id", type=int, action="append", dest="payroll_ids", default=[])
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options) -> None:
        workshop_id = options.get("workshop_id")
        payroll_ids: list[int] = list(dict.fromkeys(options.get("payroll_ids") or []))
        dry_run = bool(options.get("dry_run"))

        workshop = None
        if workshop_id is not None:
            workshop = Workshop.objects.filter(pk=workshop_id).first()
            if workshop is None:
                raise CommandError("Oficina nao encontrada.")

        queryset = CollaboratorPayroll.objects.select_related("collaborator", "financial_movement", "workshop").filter(financial_movement__isnull=True).order_by("id")
        if workshop is not None:
            queryset = queryset.filter(workshop=workshop)
        if payroll_ids:
            queryset = queryset.filter(pk__in=payroll_ids)

        payrolls = list(queryset)
        if not payrolls:
            self.stdout.write(self.style.WARNING("Nenhuma folha sem movimentacao financeira foi encontrada."))
            return

        if payroll_ids:
            found_ids = {payroll.pk for payroll in payrolls}
            missing_ids = [payroll_id for payroll_id in payroll_ids if payroll_id not in found_ids]
            if missing_ids:
                raise CommandError(f"Os ids informados nao estao sem movimentacao financeira ou nao foram encontrados: {missing_ids}")

        self.stdout.write(f"Total encontrado: {len(payrolls)}")
        for payroll in payrolls:
            self.stdout.write(f"- id={payroll.pk} oficina={payroll.workshop_id} colaborador={payroll.collaborator_id} competencia={payroll.reference_month:02d}/{payroll.reference_year} vencimento={payroll.due_date:%d/%m/%Y} total={payroll.total_amount}")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("[DRY-RUN] Nenhuma movimentacao financeira foi criada."))
            return

        created_count = 0
        for payroll in payrolls:
            reference_date = date(payroll.reference_year, payroll.reference_month, 1)
            with transaction.atomic():
                refreshed_payroll = sync_collaborator_payroll(
                    collaborator=payroll.collaborator,
                    reference_date=reference_date,
                    lock_reference=True,
                )
                if refreshed_payroll.financial_movement is None:
                    raise CommandError(f"Nao foi possivel criar a movimentacao financeira da folha {payroll.pk}.")
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f"{created_count} movimentacao(oes) financeira(s) criada(s)."))
