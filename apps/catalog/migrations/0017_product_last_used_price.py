from __future__ import annotations

from decimal import Decimal

from django.db import migrations
from djmoney.models.fields import CurrencyField, MoneyField


def _latest_entry(*entries: dict[str, object] | None) -> dict[str, object] | None:
    valid_entries = [entry for entry in entries if entry is not None]
    if not valid_entries:
        return None
    return max(valid_entries, key=lambda entry: entry["criado_em"])


def backfill_last_used_price(apps, schema_editor) -> None:
    Product = apps.get_model("catalog", "Product")
    BudgetItem = apps.get_model("budget", "BudgetItem")
    BudgetKitItemOverride = apps.get_model("budget", "BudgetKitItemOverride")
    WorkOrderItem = apps.get_model("workorder", "WorkOrderItem")
    WorkOrderKitItemOverride = apps.get_model("workorder", "WorkOrderKitItemOverride")

    for product in Product.objects.all().only("id"):
        latest_budget_item = BudgetItem.objects.filter(product_id=product.pk).order_by("-criado_em").values("criado_em", "product_selling_price", "product_selling_price_currency").first()
        latest_budget_override = BudgetKitItemOverride.objects.filter(product_id=product.pk).order_by("-criado_em").values("criado_em", "product_selling_price", "product_selling_price_currency").first()
        latest_workorder_item = WorkOrderItem.objects.filter(product_id=product.pk).order_by("-criado_em").values("criado_em", "product_selling_price", "product_selling_price_currency").first()
        latest_workorder_override = WorkOrderKitItemOverride.objects.filter(product_id=product.pk).order_by("-criado_em").values("criado_em", "product_selling_price", "product_selling_price_currency").first()

        latest_entry = _latest_entry(
            latest_budget_item,
            latest_budget_override,
            latest_workorder_item,
            latest_workorder_override,
        )
        if latest_entry is None:
            continue

        Product.objects.filter(pk=product.pk).update(
            last_used_price=latest_entry["product_selling_price"] or Decimal("0.00"),
            last_used_price_currency=latest_entry["product_selling_price_currency"] or "BRL",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0017_alter_budgetitem_options_budgetkititemoverride"),
        ("catalog", "0016_alter_product_profit_margin"),
        ("workorder", "0006_workorder_snapshot_backfill"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="last_used_price_currency",
            field=CurrencyField(choices=[("BRL", "Real Brasileiro")], default="BRL", editable=False, max_length=3),
        ),
        migrations.AddField(
            model_name="product",
            name="last_used_price",
            field=MoneyField(blank=True, decimal_places=2, max_digits=14, null=True, verbose_name="Ultimo Valor Utilizado"),
        ),
        migrations.RunPython(backfill_last_used_price, migrations.RunPython.noop),
    ]
