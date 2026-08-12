from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.stock.models import StockMovement
from apps.stock.services.workorder_stock import get_reversed_stock_movement_ids, return_workorder_stock_to_inventory
from apps.workorder.models import WorkOrder, WorkOrderStatus

logger = logging.getLogger(__name__)

RETURN_STOCK_REASON = "Estoque devolvido por O.S. reprovada/cancelada."


class Command(BaseCommand):
    help = "Valida e devolve ao estoque as peças consumidas por WorkOrders reprovadas ou canceladas."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Apenas exibe o que seria feito, sem alterar o banco.")
        parser.add_argument("--workshop-id", type=int, help="Limita a uma oficina específica.")
        parser.add_argument("--batch-size", type=int, default=50, help="Tamanho do lote para processamento (default: 50).")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        workshop_id = options.get("workshop_id")
        batch_size = options["batch_size"]

        workorder_ids = list(self._get_candidate_workorder_ids(workshop_id=workshop_id))

        if not workorder_ids:
            self.stdout.write(
                self.style.SUCCESS("Nenhuma WorkOrder reprovada/cancelada com movimentações de estoque pendentes de devolução.")
            )
            return

        self.stdout.write(
            self.style.WARNING(f"Encontradas {len(workorder_ids)} WorkOrder(s) com movimentações pendentes de devolução.")
        )

        processed = 0
        returned_count = 0
        errors = 0

        for i in range(0, len(workorder_ids), batch_size):
            batch_ids = workorder_ids[i : i + batch_size]
            batch = WorkOrder.objects.filter(pk__in=batch_ids).select_related("workshop", "budget").order_by("pk")

            for workorder in batch:
                try:
                    returned = self._process_workorder(workorder, dry_run=dry_run)
                    if returned:
                        processed += 1
                        returned_count += returned
                except Exception as exc:
                    errors += 1
                    self.stderr.write(f"Erro ao processar WorkOrder #{workorder.get_id}: {exc}")
                    logger.exception(
                        "return_stock_for_rejected_cancelled_workorders_error",
                        extra={"workorder_id": workorder.pk, "budget_id": workorder.budget_id},
                    )

        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(f"{prefix}WorkOrders processadas: {processed}, Movimentações devolvidas: {returned_count}, Erros: {errors}")
        )

    def _get_candidate_workorder_ids(self, *, workshop_id):
        queryset = (
            StockMovement.objects.filter(
                type=StockMovement.MovementType.EXIT,
                status=StockMovement.MovementStatus.APPROVED,
                workorder__status__in=[WorkOrderStatus.REJECTED, WorkOrderStatus.CANCELLED],
            )
            .exclude(pk__in=get_reversed_stock_movement_ids())
            .values_list("workorder_id", flat=True)
            .distinct()
            .order_by()
        )
        if workshop_id:
            queryset = queryset.filter(workorder__workshop_id=workshop_id)
        return queryset

    def _count_active_exit_movements(self, workorder) -> int:
        return (
            StockMovement.objects.filter(
                workorder=workorder,
                type=StockMovement.MovementType.EXIT,
                status=StockMovement.MovementStatus.APPROVED,
            )
            .exclude(pk__in=get_reversed_stock_movement_ids())
            .count()
        )

    def _process_workorder(self, workorder, *, dry_run=False):
        if dry_run:
            count = self._count_active_exit_movements(workorder)
            if count:
                self.stdout.write(f"[DRY-RUN] WorkOrder #{workorder.get_id}: devolver {count} movimentação(ões).")
            return count

        with transaction.atomic():
            locked_workorder = WorkOrder.objects.filter(pk=workorder.pk).select_for_update(skip_locked=True).first()
            if locked_workorder is None:
                self.stdout.write(f"WorkOrder #{workorder.get_id} pulada (lock não adquirido).")
                return 0

            if locked_workorder.status not in (WorkOrderStatus.REJECTED, WorkOrderStatus.CANCELLED):
                return 0

            returned = return_workorder_stock_to_inventory(workorder=locked_workorder, reason=RETURN_STOCK_REASON)
            if returned:
                self.stdout.write(
                    self.style.SUCCESS(f"WorkOrder #{locked_workorder.get_id}: {returned} movimentação(ões) revertida(s).")
                )
                logger.info(
                    "return_stock_for_rejected_cancelled_workorders_ok",
                    extra={"workorder_id": locked_workorder.pk, "budget_id": locked_workorder.budget_id, "reversed": returned},
                )
            return returned