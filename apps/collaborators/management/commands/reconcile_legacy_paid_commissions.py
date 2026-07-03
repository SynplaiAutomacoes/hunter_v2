from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, Sum

from apps.collaborators.models import CollaboratorCommissionEntry, CollaboratorPayroll
from apps.collaborators.services import mark_payroll_as_paid
from apps.workshops.models.workshops import Workshop


class Command(BaseCommand):
    help = "Reconcilia comissoes historicas pagas com folhas ainda nao pagas."

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

        payrolls_queryset = (
            CollaboratorPayroll.objects.select_related("collaborator", "financial_movement", "workshop")
            .filter(
                commission_entries__status=CollaboratorCommissionEntry.Status.PAID,
                financial_movement__isnull=False,
                financial_movement__is_paid=False,
            )
            .distinct()
            .order_by("workshop_id", "id")
        )
        if workshop is not None:
            payrolls_queryset = payrolls_queryset.filter(workshop=workshop)
        if payroll_ids:
            payrolls_queryset = payrolls_queryset.filter(pk__in=payroll_ids)

        payrolls = list(payrolls_queryset)
        if not payrolls:
            self.stdout.write(self.style.WARNING("Nenhuma folha legada com comissoes pagas pendente de reconciliacao foi encontrada."))
            return

        if payroll_ids:
            found_ids = {payroll.pk for payroll in payrolls}
            missing_ids = [payroll_id for payroll_id in payroll_ids if payroll_id not in found_ids]
            if missing_ids:
                raise CommandError(f"Os ids informados nao possuem comissoes legadas pagas pendentes ou nao foram encontrados: {missing_ids}")

        legacy_commissions = CollaboratorCommissionEntry.objects.filter(
            payroll__in=payrolls,
            status=CollaboratorCommissionEntry.Status.PAID,
        ).order_by("workshop_id", "payroll_id", "id")
        grouped_rows = list(
            legacy_commissions.values(
                "payroll_id",
                "workshop_id",
                "collaborator_id",
                "reference_month",
                "reference_year",
                "payroll__financial_movement_id",
            )
            .annotate(total_entries=Count("id"), total_amount=Sum("commission_amount"))
            .order_by("workshop_id", "payroll_id")
        )

        self.stdout.write(f"Folhas encontradas: {len(grouped_rows)}")
        for row in grouped_rows:
            self.stdout.write("- folha={payroll_id} oficina={workshop_id} colaborador={collaborator_id} competencia={reference_month:02d}/{reference_year} movimentacao={payroll__financial_movement_id} comissoes={total_entries} total={total_amount}".format(**row))

        commission_ids = list(legacy_commissions.values_list("id", flat=True))
        self.stdout.write(f"Comissoes afetadas ({len(commission_ids)}): {commission_ids}")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("[DRY-RUN] Nenhuma folha foi marcada como paga."))
            return

        reconciled_count = 0
        for payroll in payrolls:
            with transaction.atomic():
                refreshed_payroll = mark_payroll_as_paid(payroll=payroll)
                if refreshed_payroll.financial_movement is None or not refreshed_payroll.financial_movement.is_paid:
                    raise CommandError(f"Nao foi possivel reconciliar a folha {payroll.pk}.")
                reconciled_count += 1

        self.stdout.write(self.style.SUCCESS(f"{reconciled_count} folha(s) reconciliada(s) como paga(s)."))
