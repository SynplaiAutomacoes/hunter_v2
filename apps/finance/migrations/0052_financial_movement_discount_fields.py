from __future__ import annotations

from decimal import Decimal

from django.db import migrations, models
import django.utils.timezone
import djmoney.models.fields


def backfill_financial_movement_discount_fields(apps, schema_editor):
    FinancialMovement = apps.get_model("finance", "FinancialMovement")
    pending = []
    for movement in FinancialMovement.objects.all().only("pk", "amount", "amount_currency", "criado_em").iterator(chunk_size=500):
        movement.gross_amount = movement.amount
        movement.gross_amount_currency = movement.amount_currency
        movement.entry_date = movement.criado_em.date()
        pending.append(movement)
        if len(pending) >= 500:
            FinancialMovement.objects.bulk_update(pending, ["gross_amount", "gross_amount_currency", "entry_date"])
            pending.clear()
    if pending:
        FinancialMovement.objects.bulk_update(pending, ["gross_amount", "gross_amount_currency", "entry_date"])


class Migration(migrations.Migration):
    dependencies = [("finance", "0051_nfe_transport_support")]

    operations = [
        migrations.AddField(
            model_name="financialmovement",
            name="discount_mode",
            field=models.CharField(choices=[("NONE", "Sem desconto"), ("AMOUNT", "Desconto em reais (R$)"), ("PERCENTAGE", "Desconto em percentual (%)")], default="NONE", max_length=12, verbose_name="Tipo de Desconto"),
        ),
        migrations.AddField(
            model_name="financialmovement",
            name="discount_percentage",
            field=models.DecimalField(decimal_places=4, default=Decimal("0.00"), max_digits=7, verbose_name="Desconto (%)"),
        ),
        migrations.AddField(
            model_name="financialmovement",
            name="discount_value",
            field=djmoney.models.fields.MoneyField(decimal_places=2, default=0, max_digits=14, verbose_name="Desconto (R$)"),
        ),
        migrations.AddField(
            model_name="financialmovement",
            name="discount_value_currency",
            field=djmoney.models.fields.CurrencyField(choices=[("BRL", "Real Brasileiro")], default="BRL", editable=False, max_length=3),
        ),
        migrations.AddField(
            model_name="financialmovement",
            name="entry_date",
            field=models.DateField(default=django.utils.timezone.localdate, verbose_name="Data de Lançamento"),
        ),
        migrations.AddField(
            model_name="financialmovement",
            name="gross_amount",
            field=djmoney.models.fields.MoneyField(blank=True, decimal_places=2, max_digits=14, null=True, verbose_name="Valor Bruto"),
        ),
        migrations.AddField(
            model_name="financialmovement",
            name="gross_amount_currency",
            field=djmoney.models.fields.CurrencyField(choices=[("BRL", "Real Brasileiro")], default="BRL", editable=False, max_length=3, null=True),
        ),
        migrations.RunPython(backfill_financial_movement_discount_fields, migrations.RunPython.noop),
    ]
