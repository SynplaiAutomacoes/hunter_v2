from __future__ import annotations

from django.db.models import Case, F, IntegerField, Sum, Value, When
from django.db.models.functions import Coalesce

from apps.stock.models import StockMovement, StockProduct


def calculate_approved_stock_balance(*, stock_product: StockProduct) -> int:
    """Calcula o saldo a partir das movimentações aprovadas do produto."""
    balance = StockMovement.objects.filter(
        stock_product=stock_product,
        status=StockMovement.MovementStatus.APPROVED,
    ).aggregate(
        balance=Coalesce(
            Sum(
                Case(
                    When(type=StockMovement.MovementType.ENTRY, then=F("quantity")),
                    When(type=StockMovement.MovementType.EXIT, then=-F("quantity")),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            ),
            Value(0),
        )
    )["balance"]
    return int(balance)


def recover_missing_stock_balance(*, stock_product: StockProduct) -> int:
    """Recupera saldos legados ausentes sem sobrescrever saldos já preenchidos."""
    if stock_product.current_quantity is not None:
        return stock_product.current_quantity

    balance = calculate_approved_stock_balance(stock_product=stock_product)
    stock_product.current_quantity = balance
    stock_product.save(update_fields=["current_quantity"])
    return balance
