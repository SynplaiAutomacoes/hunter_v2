# Generated manually because the local Python virtual environment is unavailable.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
from djmoney.models.fields import CurrencyField, MoneyField


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0066_merge_fiscaldocument_options_and_partial_payment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FinancialTransfer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="Data de Criação")),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="Data de Atualização")),
                ("transfer_date", models.DateField(default=django.utils.timezone.localdate, verbose_name="Data da transferência")),
                ("amount_currency", CurrencyField(choices=[("BRL", "Real Brasileiro")], default="BRL", editable=False, max_length=3)),
                ("amount", MoneyField(decimal_places=2, max_digits=14, verbose_name="Valor")),
                ("description", models.TextField(blank=True, verbose_name="Observação")),
                ("destination_account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="incoming_transfers", to="finance.bankaccount")),
                ("source_account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="outgoing_transfers", to="finance.bankaccount")),
                ("user", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("workshop", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="financial_transfers", to="workshops.workshop")),
            ],
            options={
                "verbose_name": "Transferência entre contas",
                "verbose_name_plural": "Transferências entre contas",
                "indexes": [models.Index(fields=["workshop", "transfer_date"], name="finance_fin_worksho_1288f9_idx")],
                "constraints": [models.CheckConstraint(condition=~models.Q(source_account=models.F("destination_account")), name="financial_transfer_distinct_accounts")],
            },
        ),
    ]
