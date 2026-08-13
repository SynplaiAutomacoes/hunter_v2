from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.finance.models.bank_account import BankAccount
from apps.finance.models.financial_movement import FinancialMovement
from apps.workshops.models.workshops import Workshop


class Command(BaseCommand):
    help = "Associa a conta bancaria (padrao STONE) as movimentacoes financeiras conciliadas e sem conta bancaria de uma oficina."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--workshop-id", type=int, required=True, help="ID da oficina cujas movimentacoes serao atualizadas.")
        parser.add_argument("--bank-name", type=str, default="stone", help="Substring do nome da conta bancaria a associar (case insensitive).")
        parser.add_argument("--dry-run", action="store_true", help="Apenas exibe o total sem alterar o banco.")

    def handle(self, *args, **options) -> None:
        workshop_id = options["workshop_id"]
        bank_name = options["bank_name"]
        dry_run = bool(options["dry_run"])

        workshop = Workshop.objects.filter(pk=workshop_id).first()
        if workshop is None:
            raise CommandError(f"Oficina {workshop_id} nao encontrada.")

        accounts = list(BankAccount.objects.filter(workshop=workshop, is_active=True, bank_name__icontains=bank_name).order_by("id"))
        if not accounts:
            raise CommandError(f"Nenhuma conta bancaria ativa com nome contendo '{bank_name}' encontrada para a oficina {workshop_id}.")
        if len(accounts) > 1:
            raise CommandError(f"Mais de uma conta bancaria corresponde a '{bank_name}' na oficina {workshop_id}: {[account.pk for account in accounts]}.")

        bank_account = accounts[0]
        movements = FinancialMovement.objects.filter(workshop=workshop, is_reconciled=True, bank_account__isnull=True)
        total = movements.count()

        self.stdout.write(f"Oficina: {workshop} (id={workshop.pk})")
        self.stdout.write(f"Conta bancaria a associar: {bank_account} (id={bank_account.pk}, banco={bank_account.bank_name})")
        self.stdout.write(f"Movimentacoes conciliadas sem conta bancaria: {total}")

        if total == 0:
            self.stdout.write(self.style.WARNING("Nenhuma movimentacao conciliada sem conta bancaria encontrada."))
            return

        if dry_run:
            self.stdout.write(self.style.SUCCESS("[DRY-RUN] Nenhuma movimentacao foi alterada."))
            return

        with transaction.atomic():
            updated = movements.update(bank_account=bank_account)

        self.stdout.write(self.style.SUCCESS(f"{updated} movimentacao(oes) atualizada(s) com a conta bancaria {bank_account}."))