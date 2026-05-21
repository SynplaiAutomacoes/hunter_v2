from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.collaborators.services import sync_workorder_collaborator_payrolls
from apps.finance.models.financial_movement import FinancialMovement
from apps.stock.models import StockMovement
from apps.workorder.models import WORKORDER_REOPENABLE_STATUSES, WorkOrder, WorkOrderError, WorkOrderHistory, WorkOrderStatus


class WorkOrderReopenError(Exception):
    pass


def _reverse_financial_direction(direction: str | None) -> str | None:
    if direction == FinancialMovement.MovementDirection.CREDIT:
        return FinancialMovement.MovementDirection.DEBIT
    if direction == FinancialMovement.MovementDirection.DEBIT:
        return FinancialMovement.MovementDirection.CREDIT
    return direction


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

        reversed_stock_ids = StockMovement.objects.filter(reversal_of__isnull=False).values_list("reversal_of_id", flat=True)

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

        reversed_financial_ids = FinancialMovement.objects.filter(reversal_of__isnull=False).values_list("reversal_of_id", flat=True)
        financial_movements = list(
            FinancialMovement.objects.select_for_update()
            .filter(
                workorder=locked_workorder,
                reversal_of__isnull=True,
                movement_kind__in=[
                    FinancialMovement.MovementKind.WORKORDER_PARENT,
                    FinancialMovement.MovementKind.WORKORDER_CARD_FEE,
                ],
            )
            .exclude(pk__in=reversed_financial_ids)
            .order_by("pk")
        )
        for financial_movement in financial_movements:
            FinancialMovement.objects.create(
                workshop=financial_movement.workshop,
                user=user,
                workorder=locked_workorder,
                workorder_payment=financial_movement.workorder_payment,
                reversal_of=financial_movement,
                source=financial_movement.source,
                collaborator=financial_movement.collaborator,
                supplier=financial_movement.supplier,
                description=f"Estorno da reabertura da O.S. #{locked_workorder.get_id}: {financial_movement.description or '-'}",
                items_observation=financial_movement.items_observation,
                direction=_reverse_financial_direction(financial_movement.direction),
                payment_method=financial_movement.payment_method,
                nf_number=financial_movement.nf_number,
                amount=financial_movement.amount,
                due_date=timezone.localdate(),
                is_paid=True,
                budget_plan=financial_movement.budget_plan,
                bank_account=financial_movement.bank_account,
                financial_observation=reason,
            )

        WorkOrderHistory.objects.create(
            workorder=locked_workorder,
            user=user,
            action=WorkOrderHistory.Action.REOPENED,
            reason=reason,
        )

        locked_workorder.reopen(reason=reason)

        sync_workorder_collaborator_payrolls(workorder=locked_workorder)
