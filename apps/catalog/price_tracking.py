from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

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


def _calculate_profit_margin_percent(*, cost_price: Money | None, selling_price: Money | None) -> Decimal:
    cost_amount = Decimal(getattr(cost_price, "amount", Decimal("0")) or Decimal("0"))
    selling_amount = Decimal(getattr(selling_price, "amount", Decimal("0")) or Decimal("0"))
    if selling_amount <= 0:
        return Decimal("0.00")
    return ((selling_amount - cost_amount) / selling_amount * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _assign_money_if_changed(*, model_instance: object, field_name: str, price: Money | None, update_fields: list[str]) -> bool:
    if price is None:
        return False
    if getattr(model_instance, field_name, None) == price:
        return False
    setattr(model_instance, field_name, Money(price.amount, price.currency))
    update_fields.extend([field_name, f"{field_name}_currency"])
    return True


def apply_product_import_prices(*, product: Product | None, purchase_price: Money | None, selling_price: Money | None) -> None:
    if product is None:
        return

    update_fields: list[str] = []
    cost_changed = _assign_money_if_changed(model_instance=product, field_name="cost_price", price=purchase_price, update_fields=update_fields)
    selling_changed = _assign_money_if_changed(model_instance=product, field_name="selling_price", price=selling_price, update_fields=update_fields)
    _assign_money_if_changed(model_instance=product, field_name="last_purchase_price", price=purchase_price, update_fields=update_fields)
    _assign_money_if_changed(model_instance=product, field_name="last_used_price", price=selling_price, update_fields=update_fields)

    if cost_changed or selling_changed:
        product.profit_margin = _calculate_profit_margin_percent(cost_price=product.cost_price, selling_price=product.selling_price)
        update_fields.append("profit_margin")

    if update_fields:
        product.save(update_fields=update_fields)


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
