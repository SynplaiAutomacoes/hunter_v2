from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import migrations


def _parse_product_id(raw_product_id: object) -> int | None:
    if raw_product_id in (None, ""):
        return None
    try:
        return int(raw_product_id)
    except (TypeError, ValueError):
        return None


def _parse_purchase_amount(raw_value: object) -> Decimal | None:
    if raw_value in (None, ""):
        return None
    try:
        amount = Decimal(str(raw_value))
    except (InvalidOperation, ValueError):
        return None
    if amount <= 0:
        return None
    return amount


def backfill_product_cost_from_imports(apps, schema_editor) -> None:
    from djmoney.money import Money

    from apps.catalog.models import Product
    from apps.catalog.price_tracking import apply_product_import_prices
    from apps.stock.models import StockImport

    latest_purchase_by_product: dict[int, Money] = {}

    completed_imports = StockImport.objects.filter(status=StockImport.ImportStatus.COMPLETED).order_by("criado_em", "pk").only("items_data")

    for stock_import in completed_imports.iterator(chunk_size=200):
        for item in stock_import.items_data or []:
            product_id = _parse_product_id(item.get("linked_product_id"))
            if product_id is None:
                continue
            purchase_amount = _parse_purchase_amount(item.get("valor"))
            if purchase_amount is None:
                continue
            latest_purchase_by_product[product_id] = Money(purchase_amount, "BRL")

    for product_id, purchase_price in latest_purchase_by_product.items():
        product = Product.objects.filter(pk=product_id).first()
        if product is None:
            continue
        apply_product_import_prices(product=product, purchase_price=purchase_price, selling_price=None)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0033_service_custo_de_frete"),
        ("stock", "0019_merge_purchase_return_and_stock_adjustment"),
    ]

    operations = [
        migrations.RunPython(backfill_product_cost_from_imports, migrations.RunPython.noop),
    ]
