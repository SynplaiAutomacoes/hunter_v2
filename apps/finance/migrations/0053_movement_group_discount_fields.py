from decimal import Decimal

from django.db import migrations, models
from django.db.models import Sum
import djmoney.models.fields


def backfill_movement_group_amounts(apps, schema_editor):
    MovementGroup = apps.get_model("finance", "MovementGroup")
    FinancialMovement = apps.get_model("finance", "FinancialMovement")
    pending = []
    for group in MovementGroup.objects.all().iterator(chunk_size=500):
        total = (
            FinancialMovement.objects.filter(movement_group_id=group.pk, movement_kind="GROUP_PARENT")
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        group.gross_amount = total
        group.gross_amount_currency = "BRL"
        group.net_amount = total
        group.net_amount_currency = "BRL"
        pending.append(group)
        if len(pending) >= 500:
            MovementGroup.objects.bulk_update(pending, ["gross_amount", "gross_amount_currency", "net_amount", "net_amount_currency"])
            pending.clear()
    if pending:
        MovementGroup.objects.bulk_update(pending, ["gross_amount", "gross_amount_currency", "net_amount", "net_amount_currency"])


class Migration(migrations.Migration):
    dependencies = [("finance", "0052_financial_movement_discount_fields")]

    operations = [
        migrations.AddField(
            model_name="movementgroup",
            name="discount_mode",
            field=models.CharField(choices=[("NONE", "Sem desconto"), ("AMOUNT", "Desconto em reais (R$)"), ("PERCENTAGE", "Desconto em percentual (%)")], default="NONE", max_length=12, verbose_name="Tipo de Desconto"),
        ),
        migrations.AddField(
            model_name="movementgroup",
            name="discount_percentage",
            field=models.DecimalField(decimal_places=4, default=Decimal("0.00"), max_digits=7, verbose_name="Desconto (%)"),
        ),
        migrations.AddField(
            model_name="movementgroup",
            name="discount_value",
            field=djmoney.models.fields.MoneyField(decimal_places=2, default=0, max_digits=14, verbose_name="Desconto (R$)"),
        ),
        migrations.AddField(
            model_name="movementgroup",
            name="discount_value_currency",
            field=djmoney.models.fields.CurrencyField(choices=[("BRL", "Real Brasileiro")], default="BRL", editable=False, max_length=3),
        ),
        migrations.AddField(
            model_name="movementgroup",
            name="gross_amount",
            field=djmoney.models.fields.MoneyField(decimal_places=2, default=0, max_digits=14, verbose_name="Valor Bruto"),
        ),
        migrations.AddField(
            model_name="movementgroup",
            name="gross_amount_currency",
            field=djmoney.models.fields.CurrencyField(choices=[("BRL", "Real Brasileiro")], default="BRL", editable=False, max_length=3),
        ),
        migrations.AddField(
            model_name="movementgroup",
            name="net_amount",
            field=djmoney.models.fields.MoneyField(decimal_places=2, default=0, max_digits=14, verbose_name="Valor Líquido"),
        ),
        migrations.AddField(
            model_name="movementgroup",
            name="net_amount_currency",
            field=djmoney.models.fields.CurrencyField(choices=[("BRL", "Real Brasileiro")], default="BRL", editable=False, max_length=3),
        ),
        migrations.RunPython(backfill_movement_group_amounts, migrations.RunPython.noop),
    ]
