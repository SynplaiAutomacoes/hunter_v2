from __future__ import annotations

from dataclasses import dataclass

from djmoney.money import Money

from apps.catalog.models.products import Product


@dataclass(frozen=True)
class ProductPriceWarning:
    attempted_price: Money
    last_used_price: Money

    @property
    def message(self) -> str:
        return f"Insira um valor maior que {self.last_used_price}"


def build_product_price_warning(*, product: Product, attempted_price: Money | None) -> ProductPriceWarning | None:
    last_used_price = getattr(product, "last_used_price", None)
    if not product.pk or attempted_price is None or last_used_price is None:
        return None

    if attempted_price < last_used_price:
        return ProductPriceWarning(attempted_price=attempted_price, last_used_price=last_used_price)

    return None


def record_product_last_used_price(*, product: Product | None, price: Money | None) -> None:
    if product is None or price is None:
        return

    if getattr(product, "last_used_price", None) == price:
        return

    product.last_used_price = Money(price.amount, price.currency)
    product.save(update_fields=["last_used_price", "last_used_price_currency"])
