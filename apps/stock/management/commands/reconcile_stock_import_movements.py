from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from djmoney.money import Money

from apps.finance.models.financial_movement import FinancialMovement
from apps.finance.models.payment_method import PaymentMethod
from apps.sources.models import Source
from apps.stock.financial_entries import resolve_import_budget_plan
from apps.stock.models import StockImport


class Command(BaseCommand):
    help = "Reconcilia FinancialMovements órfãos de importações de estoque concluídas."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Apenas exibe o que seria feito, sem alterar o banco.")
        parser.add_argument("--workshop-id", type=int, help="Limita a uma oficina específica.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        workshop_id = options.get("workshop_id")

        queryset = StockImport.objects.filter(status=StockImport.ImportStatus.COMPLETED)
        if workshop_id:
            queryset = queryset.filter(workshop_id=workshop_id)

        created_count = 0
        skipped_count = 0

        for stock_import in queryset.select_related("workshop", "user"):
            payments_data = stock_import.payments_data or []
            for pay in payments_data:
                if pay.get("entry_type") != "payment":
                    continue

                financial_movement_id = pay.get("financial_movement_id")
                if not financial_movement_id:
                    continue

                if FinancialMovement.objects.filter(pk=financial_movement_id).exists():
                    skipped_count += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f"[DRY-RUN] Criaria FinancialMovement para importação #{stock_import.pk} "
                        f"(NF: {stock_import.nf_number_display}, valor: {pay.get('total_paid')})"
                    )
                    created_count += 1
                    continue

                with transaction.atomic():
                    workshop = stock_import.workshop
                    resolved_nf_number = stock_import.nf_number_display or "S/N"
                    source_name = stock_import.supplier_name or "Fornecedor da Importação"
                    source_cnpj = stock_import.supplier_cnpj or ""
                    source, _ = Source.objects.get_or_create(workshop=workshop, name=source_name, defaults={"cnpj": source_cnpj})

                    method_id = pay.get("method")
                    payment_method_obj = PaymentMethod.objects.filter(id=method_id, workshop=workshop).first()
                    if not payment_method_obj:
                        self.stderr.write(f"PaymentMethod {method_id} não encontrado para oficina {workshop.pk}. Pulando.")
                        continue

                    budget_plan = resolve_import_budget_plan(workshop=workshop, budget_plan_id=pay.get("budget_plan_id"))
                    if budget_plan is None:
                        self.stderr.write(
                            f"Plano orçamentário {pay.get('budget_plan_id')} não encontrado para oficina {workshop.pk}. Pulando."
                        )
                        continue

                    total_val = Decimal(str(pay.get("total_paid", 0)))
                    payment_date = pay.get("payment_date")

                    FinancialMovement.objects.create(
                        workshop=workshop,
                        user=stock_import.user,
                        source=source,
                        direction=FinancialMovement.MovementDirection.DEBIT,
                        description=f"Pagamento Importação de Estoque - NF: {resolved_nf_number}",
                        payment_method=payment_method_obj,
                        budget_plan=budget_plan,
                        nf_number=stock_import.nf_number,
                        amount=Money(total_val, "BRL"),
                        due_date=payment_date,
                        is_paid=False,
                    )
                    created_count += 1

        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}Criados: {created_count}, Já existentes: {skipped_count}"))
