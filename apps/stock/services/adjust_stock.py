from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.text_normalization import sentence_case
from apps.stock.models import StockMovement, StockProduct


def adjust_stock_quantity(
    *,
    stock_product: StockProduct,
    new_quantity: int,
    reason: str,
    user: AbstractBaseUser | None,
) -> StockMovement:
    normalized_reason = sentence_case(str(reason or "").strip())
    if not normalized_reason:
        raise ValidationError("Informe o motivo do ajuste de estoque.")

    if new_quantity < 0:
        raise ValidationError("A quantidade em estoque não pode ser negativa.")

    with transaction.atomic():
        locked_stock = StockProduct.objects.select_for_update().get(pk=stock_product.pk)
        current_quantity = locked_stock.current_quantity
        delta = new_quantity - current_quantity

        if delta == 0:
            raise ValidationError("A quantidade informada é igual ao estoque atual. Nada a ajustar.")

        locked_stock.current_quantity = new_quantity
        locked_stock.save(update_fields=["current_quantity"])

        return StockMovement.objects.create(
            workshop=locked_stock.workshop,
            stock_product=locked_stock,
            type=StockMovement.MovementType.ENTRY if delta > 0 else StockMovement.MovementType.EXIT,
            quantity=abs(delta),
            reason=normalized_reason,
            is_stock_adjustment=True,
            status=StockMovement.MovementStatus.APPROVED,
            transcation_by=user if user is not None and getattr(user, "is_authenticated", False) else None,
            supplier=None,
        )
