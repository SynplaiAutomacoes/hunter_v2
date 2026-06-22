from __future__ import annotations

from decimal import Decimal

from django.db import migrations
from djmoney.models.fields import CurrencyField, MoneyField


def backfill_last_used_price(apps, schema_editor) -> None:
    Service = apps.get_model("catalog", "Service")
    BudgetItem = apps.get_model("budget", "BudgetItem")
    BudgetKitItemOverride = apps.get_model("budget", "BudgetKitItemOverride")
    WorkOrderItem = apps.get_model("workorder", "WorkOrderItem")
    WorkOrderKitItemOverride = apps.get_model("workorder", "WorkOrderKitItemOverride")

    # Collect the latest entry per service_id from each source in 4 bulk queries
    # (avoids N+1 — one query per source, not one per service)
    all_latest: dict[int, tuple[Decimal, str, object]] = {}

    for source_model in [BudgetItem, BudgetKitItemOverride, WorkOrderItem, WorkOrderKitItemOverride]:
        seen: set[int] = set()
        entries = (
            source_model.objects
            .filter(service_id__isnull=False)
            .order_by("service_id", "-criado_em")
            .values_list("service_id", "service_selling_price", "service_selling_price_currency", "criado_em")
            .iterator()
        )
        for sid, amount, currency, criado_em in entries:
            if sid in seen:
                continue
            seen.add(sid)
            existing = all_latest.get(sid)
            if existing is None or criado_em > existing[2]:
                all_latest[sid] = (amount or Decimal("0.00"), currency or "BRL", criado_em)

    # Update each service — fallback to its own selling_price when no history exists
    for service in Service.objects.only("id", "selling_price", "selling_price_currency").iterator():
        entry = all_latest.get(service.pk)
        if entry is not None:
            price, currency, _ = entry
        else:
            price = service.selling_price.amount if service.selling_price else Decimal("0.00")
            currency = "BRL"

        Service.objects.filter(pk=service.pk).update(
            last_used_price=price,
            last_used_price_currency=currency,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0029_copy_fipe_data_from_customer"),
    ]

    operations = [
        migrations.AddField(
            model_name="service",
            name="last_used_price_currency",
            field=CurrencyField(choices=[("BRL", "Real Brasileiro")], default="BRL", editable=False, max_length=3),
        ),
        migrations.AddField(
            model_name="service",
            name="last_used_price",
            field=MoneyField(blank=True, decimal_places=2, max_digits=14, null=True, verbose_name="Ultimo Valor Utilizado"),
        ),
        migrations.RunPython(backfill_last_used_price, migrations.RunPython.noop),
    ]
