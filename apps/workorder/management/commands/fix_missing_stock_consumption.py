from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.stock.models import StockMovement, StockProduct
from apps.workorder.approval import _collect_required_products
from apps.workorder.models import WorkOrder, WorkOrderStatus

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Consome estoque retroativo para WorkOrders aprovadas sem StockMovement do tipo EXIT."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Apenas exibe o que seria feito, sem alterar o banco.")
        parser.add_argument("--workshop-id", type=int, help="Limita a uma oficina específica.")
        parser.add_argument("--batch-size", type=int, default=50, help="Tamanho do lote para processamento (default: 50).")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        workshop_id = options.get("workshop_id")
        batch_size = options["batch_size"]

        queryset = (
            WorkOrder.objects.filter(status=WorkOrderStatus.APPROVED)
            .exclude(stock_movements__type=StockMovement.MovementType.EXIT)
            .select_related("workshop", "budget")
        )

        if workshop_id:
            queryset = queryset.filter(workshop_id=workshop_id)

        total = queryset.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nenhuma WorkOrder pendente de consumo encontrada."))
            return

        self.stdout.write(self.style.WARNING(f"Encontradas {total} WorkOrder(s) sem consumo de estoque."))

        processed = 0
        errors = 0
        workorder_ids = list(queryset.values_list("pk", flat=True))

        for i in range(0, len(workorder_ids), batch_size):
            batch_ids = workorder_ids[i : i + batch_size]
            batch = WorkOrder.objects.filter(pk__in=batch_ids).select_related("workshop", "budget")

            for workorder in batch:
                try:
                    self._process_workorder(workorder, dry_run=dry_run)
                    processed += 1
                except Exception as exc:
                    errors += 1
                    self.stderr.write(f"Erro ao processar WorkOrder #{workorder.get_id}: {exc}")
                    logger.exception(
                        "fix_missing_stock_consumption_error",
                        extra={"workorder_id": workorder.pk, "budget_id": workorder.budget_id},
                    )

        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}Processadas: {processed}, Erros: {errors}"))

    def _process_workorder(self, workorder, *, dry_run=False):
        if StockMovement.objects.filter(workorder=workorder, type=StockMovement.MovementType.EXIT).exists():
            return

        required_quantities, product_names, invalid_ncm_products = _collect_required_products(workorder)

        if dry_run:
            self.stdout.write(f"[DRY-RUN] WorkOrder #{workorder.get_id}: consumir {dict(required_quantities)}")
            logger.info(
                "fix_missing_stock_consumption_dry_run",
                extra={
                    "workorder_id": workorder.pk,
                    "budget_id": workorder.budget_id,
                    "required_quantities": dict(required_quantities),
                },
            )
            return

        with transaction.atomic():
            locked_workorder = WorkOrder.objects.filter(pk=workorder.pk).select_for_update(skip_locked=True).first()
            if locked_workorder is None:
                self.stdout.write(f"WorkOrder #{workorder.get_id} pulada (lock não adquirido).")
                return

            if StockMovement.objects.filter(workorder=locked_workorder, type=StockMovement.MovementType.EXIT).exists():
                return

            stock_entries = StockProduct.objects.select_for_update().filter(
                workshop=locked_workorder.workshop,
                product_id__in=list(required_quantities.keys()),
            )
            stock_by_product_id = {entry.product_id: entry for entry in stock_entries}

            movement_date = locked_workorder.delivered_at or timezone.now()

            for product_id, required_quantity in required_quantities.items():
                stock_entry = stock_by_product_id.get(product_id)
                if stock_entry is None:
                    self.stderr.write(
                        f"WorkOrder #{locked_workorder.get_id}: produto {product_names.get(product_id, product_id)} "
                        f"sem estoque cadastrado."
                    )
                    logger.warning(
                        "fix_missing_stock_consumption_no_stock_product",
                        extra={
                            "workorder_id": locked_workorder.pk,
                            "product_id": product_id,
                            "product_name": product_names.get(product_id),
                        },
                    )
                    continue

                available = stock_entry.current_quantity
                if available < required_quantity:
                    self.stderr.write(
                        f"WorkOrder #{locked_workorder.get_id}: produto '{product_names.get(product_id, product_id)}' "
                        f"estoque insuficiente ({available} < {required_quantity})."
                    )
                    logger.warning(
                        "fix_missing_stock_consumption_insufficient_stock",
                        extra={
                            "workorder_id": locked_workorder.pk,
                            "product_id": product_id,
                            "product_name": product_names.get(product_id),
                            "available": available,
                            "required": required_quantity,
                        },
                    )
                    continue

                stock_entry.current_quantity -= required_quantity
                stock_entry.save(update_fields=["current_quantity"])

                movement = StockMovement.objects.create(
                    workshop=locked_workorder.workshop,
                    stock_product=stock_entry,
                    workorder=locked_workorder,
                    type=StockMovement.MovementType.EXIT,
                    quantity=required_quantity,
                    reason="Fechamento de O.S.",
                    status=StockMovement.MovementStatus.APPROVED,
                    transcation_by=None,
                )
                StockMovement.objects.filter(pk=movement.pk).update(
                    criado_em=movement_date,
                    atualizado_em=movement_date,
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"WorkOrder #{locked_workorder.get_id}: estoque consumido com sucesso "
                    f"({dict(required_quantities)})."
                )
            )
            logger.info(
                "fix_missing_stock_consumption_ok",
                extra={
                    "workorder_id": locked_workorder.pk,
                    "budget_id": locked_workorder.budget_id,
                    "consumed": dict(required_quantities),
                    "movement_date": movement_date.isoformat(),
                },
            )
