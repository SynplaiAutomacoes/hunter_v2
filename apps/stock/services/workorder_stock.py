from __future__ import annotations

from typing import TYPE_CHECKING

from apps.stock.models import StockMovement

if TYPE_CHECKING:
    from apps.workorder.models import WorkOrder


def get_reversed_stock_movement_ids() -> list[int]:
    return list(StockMovement.objects.filter(reversal_of__isnull=False).values_list("reversal_of_id", flat=True))


def get_active_exit_movements(*, workorder: WorkOrder):
    """Movimentações EXIT de consumo ainda ativas (APROVADO e sem reversão).

    Essa é a validação feita antes de devolver as peças para a oficina: a
    movimentação precisa pertencer à O.S., ser do tipo EXIT, estar com status
    APROVADO e ainda não ter sido revertida por um ENTRY de `reversal_of`.
    """
    return (
        StockMovement.objects.select_for_update()
        .select_related("stock_product", "stock_product__product")
        .filter(
            workorder=workorder,
            type=StockMovement.MovementType.EXIT,
            status=StockMovement.MovementStatus.APPROVED,
        )
        .exclude(pk__in=get_reversed_stock_movement_ids())
        .order_by("pk")
    )


def has_unreversed_exit_movements(*, workorder: WorkOrder) -> bool:
    return (
        StockMovement.objects.filter(
            workorder=workorder,
            type=StockMovement.MovementType.EXIT,
            status=StockMovement.MovementStatus.APPROVED,
        )
        .exclude(pk__in=get_reversed_stock_movement_ids())
        .exists()
    )


def return_workorder_stock_to_inventory(*, workorder: WorkOrder, user=None, reason: str = "") -> int:
    """Valida e devolve ao estoque as peças consumidas por uma O.S.

    Cria uma movimentação ENTRY de reversão para cada EXIT ativo (APROVADO e
    não revertido) e incrementa a quantidade do produto no estoque da oficina.

    Retorna a quantidade de movimentações revertidas.
    """
    reversed_count = 0

    for movement in get_active_exit_movements(workorder=workorder):
        stock_product = movement.stock_product
        stock_product.current_quantity += movement.quantity
        stock_product.save(update_fields=["current_quantity"])

        StockMovement.objects.create(
            workshop=movement.workshop,
            stock_product=stock_product,
            workorder=workorder,
            reversal_of=movement,
            type=StockMovement.MovementType.ENTRY,
            quantity=movement.quantity,
            status=StockMovement.MovementStatus.APPROVED,
            transcation_by=user,
            supplier=movement.supplier,
            reason=reason,
        )
        reversed_count += 1

    return reversed_count
