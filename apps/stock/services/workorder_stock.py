from __future__ import annotations

from typing import TYPE_CHECKING

from apps.stock.models import StockMovement

if TYPE_CHECKING:
    from apps.workorder.models import WorkOrder


def get_reversed_stock_movement_ids() -> list[int]:
    return list(StockMovement.objects.filter(reversal_of__isnull=False).values_list("reversal_of_id", flat=True))


def has_unreversed_exit_movements(*, workorder: WorkOrder) -> bool:
    return (
        StockMovement.objects.filter(
            workorder=workorder,
            type=StockMovement.MovementType.EXIT,
        )
        .exclude(pk__in=get_reversed_stock_movement_ids())
        .exists()
    )
