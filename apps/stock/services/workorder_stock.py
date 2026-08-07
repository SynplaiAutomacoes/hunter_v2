from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from django.db.models import Sum

from apps.stock.models import StockMovement

if TYPE_CHECKING:
    from apps.workorder.models import WorkOrder


def get_reversed_stock_movement_ids() -> list[int]:
    """Retorna os IDs de movimentações que já foram estornadas (legado).

    Mantido apenas para retrocompatibilidade de código/histórico. O fluxo de
    reabertura de O.S. não usa mais estorno — ver ``get_consumed_stock_quantities``.
    """
    return list(StockMovement.objects.filter(reversal_of__isnull=False).values_list("reversal_of_id", flat=True))


def get_consumed_stock_quantities(*, workorder: WorkOrder) -> dict[int, int]:
    """Quantidade já consumida por ``product_id`` da O.S.

    Corresponde à somatória das movimentações ``EXIT`` (aprovadas) subtraídas das
    devoluções ``ENTRY`` (aprovadas) vinculadas à O.S. É a fonte da verdade usada
    pela reconciliação por delta ao re-abrir/reativar uma O.S.
    """
    rows = (
        StockMovement.objects.filter(
            workorder=workorder,
            status=StockMovement.MovementStatus.APPROVED,
        )
        .values("stock_product__product_id", "type")
        .annotate(total=Sum("quantity"))
    )
    consumed: dict[int, int] = defaultdict(int)
    for row in rows:
        product_id = row["stock_product__product_id"]
        if product_id is None:
            continue
        if row["type"] == StockMovement.MovementType.EXIT:
            consumed[product_id] += row["total"]
        elif row["type"] == StockMovement.MovementType.ENTRY:
            consumed[product_id] -= row["total"]
    return {product_id: quantity for product_id, quantity in consumed.items() if quantity != 0}


def has_unreversed_exit_movements(*, workorder: WorkOrder) -> bool:
    """Indica consumo histórico de estoque da O.S.

    Mantém semântica apenas informacional/legado: aponta que existe movimento
    ``EXIT`` aprovado na O.S. que não é referência de outra reversão. Não é mais
    usado como gate de re-consumo no fluxo de reabertura — a reconciliação é feita
    por delta entre o necessário e o já consumido (``get_consumed_stock_quantities``).
    """
    return (
        StockMovement.objects.filter(
            workorder=workorder,
            type=StockMovement.MovementType.EXIT,
        )
        .exclude(pk__in=get_reversed_stock_movement_ids())
        .exists()
    )
