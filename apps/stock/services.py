from __future__ import annotations

from typing import Iterable

from apps.stock.models import StockProduct


def get_stock_quantity(*, workshop_id: int, product_id: int) -> int:
    return (
        StockProduct.objects.filter(
            workshop_id=workshop_id,
            product_id=product_id,
        ).values_list("current_quantity", flat=True).first()
        or 0
    )


def get_stock_quantities(*, workshop, product_ids: Iterable[int]) -> dict[int, int]:
    return dict(
        StockProduct.objects.filter(
            workshop=workshop,
            product_id__in=list(product_ids),
        ).values_list("product_id", "current_quantity")
    )
