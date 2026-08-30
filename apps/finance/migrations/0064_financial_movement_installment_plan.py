from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import djmoney.models.fields


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0063_financial_movement_adjustment_choices"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FinancialMovementInstallmentPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="Data de Criação")),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="Data de Atualização")),
                ("gross_amount_currency", djmoney.models.fields.CurrencyField(choices=[("BRL", "Real Brasileiro")], default="BRL", editable=False, max_length=3)),
                ("gross_amount", djmoney.models.fields.MoneyField(decimal_places=2, max_digits=14, verbose_name="Valor Bruto Original")),
                ("adjustment_mode", models.CharField(default="NONE", max_length=12)),
                ("adjustment_value_currency", djmoney.models.fields.CurrencyField(choices=[("BRL", "Real Brasileiro")], default="BRL", editable=False, max_length=3)),
                ("adjustment_value", djmoney.models.fields.MoneyField(decimal_places=2, default=0, max_digits=14, verbose_name="Ajuste Original")),
                ("net_amount_currency", djmoney.models.fields.CurrencyField(choices=[("BRL", "Real Brasileiro")], default="BRL", editable=False, max_length=3)),
                ("net_amount", djmoney.models.fields.MoneyField(decimal_places=2, max_digits=14, verbose_name="Valor Líquido Original")),
                ("installments_count", models.PositiveSmallIntegerField(verbose_name="Quantidade de Parcelas")),
                ("user", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("workshop", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="financial_movement_installment_plans", to="workshops.workshop")),
            ],
            options={"verbose_name": "Plano de Parcelamento Financeiro", "verbose_name_plural": "Planos de Parcelamento Financeiro"},
        ),
        migrations.AddField(
            model_name="financialmovement",
            name="installment_plan",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="financial_movements", to="finance.financialmovementinstallmentplan", verbose_name="Parcelamento"),
        ),
        migrations.AddField(
            model_name="financialmovement",
            name="installment_number",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Número da Parcela"),
        ),
        migrations.AddField(
            model_name="financialmovement",
            name="installments_count",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Quantidade de Parcelas"),
        ),
    ]
