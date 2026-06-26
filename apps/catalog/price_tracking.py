from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from djmoney.money import Money

from apps.catalog.models.products import Product
from apps.catalog.models.services import Service


def _format_money(value: Money) -> str:
    amount = Decimal(getattr(value, "amount", Decimal("0.00")) or Decimal("0.00")).quantize(Decimal("0.01"))
    integer_part, decimal_part = f"{amount:.2f}".split(".")
    grouped_integer = f"{int(integer_part):,}".replace(",", ".")
    return f"R$ {grouped_integer},{decimal_part}"


@dataclass(frozen=True)
class PriceWarning:
    attempted_price: Money
    last_used_price: Money

    @property
    def message(self) -> str:
        return f"Último valor usado: {_format_money(self.last_used_price)}"


ProductPriceWarning = PriceWarning
ServicePriceWarning = PriceWarning


def _build_price_warning(*, model_instance, attempted_price: Money | None) -> PriceWarning | None:
    last_used_price = getattr(model_instance, "last_used_price", None)
    if not model_instance.pk or attempted_price is None or last_used_price is None:
        return None

    if attempted_price < last_used_price:
        return PriceWarning(attempted_price=attempted_price, last_used_price=last_used_price)

    return None


def build_product_price_warning(*, product: Product, attempted_price: Money | None) -> PriceWarning | None:
    return _build_price_warning(model_instance=product, attempted_price=attempted_price)


def build_service_price_warning(*, service: Service, attempted_price: Money | None) -> PriceWarning | None:
    return _build_price_warning(model_instance=service, attempted_price=attempted_price)


def record_product_last_purchase_price(*, product: Product | None, price: Money | None) -> None:
    if product is None or price is None:
        return

    if getattr(product, "last_purchase_price", None) == price:
        return

    product.last_purchase_price = Money(price.amount, price.currency)
    product.save(update_fields=["last_purchase_price", "last_purchase_price_currency"])


def _record_last_used_price(*, model_instance, price: Money | None) -> None:
    if model_instance is None or price is None:
        return

    if getattr(model_instance, "last_used_price", None) == price:
        return

    model_instance.last_used_price = Money(price.amount, price.currency)
    model_instance.save(update_fields=["last_used_price", "last_used_price_currency"])


def record_product_last_used_price(*, product: Product | None, price: Money | None) -> None:
    _record_last_used_price(model_instance=product, price=price)


def record_service_last_used_price(*, service: Service | None, price: Money | None) -> None:
    _record_last_used_price(model_instance=service, price=price)
