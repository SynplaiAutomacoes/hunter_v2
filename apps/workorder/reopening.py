from __future__ import annotations

from django.db import transaction

from apps.collaborators.services import sync_workorder_collaborator_payrolls
from apps.finance.models.financial_movement import FinancialMovement
from apps.stock.models import StockMovement
from apps.stock.services.workorder_stock import get_reversed_stock_movement_ids
from apps.workorder.models import WORKORDER_REOPENABLE_STATUSES, WorkOrder, WorkOrderHistory


class WorkOrderReopenError(Exception):
    pass


def reopen_workorder(*, workorder: WorkOrder, user, reason: str) -> None:
    if not workorder.can_reopen:
        raise WorkOrderReopenError("Somente ordens de serviço entregues, canceladas ou rejeitadas podem ser reabertas.")

    reason = str(reason or "").strip()
    if not reason:
        raise WorkOrderReopenError("Informe a justificativa para reabrir a O.S.")

    with transaction.atomic():
        locked_workorder = WorkOrder.objects.select_for_update().select_related("budget", "workshop").get(pk=workorder.pk)
        if locked_workorder.status not in WORKORDER_REOPENABLE_STATUSES:
            raise WorkOrderReopenError("Somente ordens de serviço entregues, canceladas ou rejeitadas podem ser reabertas.")

        reversed_stock_ids = get_reversed_stock_movement_ids()

        stock_movements = list(
            StockMovement.objects.select_for_update()
            .select_related("stock_product", "stock_product__product")
            .filter(
                workorder=locked_workorder,
                type=StockMovement.MovementType.EXIT,
                status=StockMovement.MovementStatus.APPROVED,
            )
            .exclude(pk__in=reversed_stock_ids)
            .order_by("pk")
        )
        for movement in stock_movements:
            stock_product = movement.stock_product
            stock_product.current_quantity += movement.quantity
            stock_product.save(update_fields=["current_quantity"])
            StockMovement.objects.create(
                workshop=movement.workshop,
                stock_product=stock_product,
                workorder=locked_workorder,
                reversal_of=movement,
                type=StockMovement.MovementType.ENTRY,
                quantity=movement.quantity,
                status=StockMovement.MovementStatus.APPROVED,
                transcation_by=user,
                supplier=movement.supplier,
            )

        FinancialMovement.objects.select_for_update().filter(
            workorder=locked_workorder,
            movement_kind__in=[
                FinancialMovement.MovementKind.WORKORDER_PARENT,
                FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
            ],
        ).delete()

        WorkOrderHistory.objects.create(
            workorder=locked_workorder,
            user=user,
            action=WorkOrderHistory.Action.REOPENED,
            reason=reason,
        )

        locked_workorder.reopen(reason=reason)

        sync_workorder_collaborator_payrolls(workorder=locked_workorder)
