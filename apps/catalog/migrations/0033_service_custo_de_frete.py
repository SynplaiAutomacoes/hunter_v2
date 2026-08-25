from django.db import migrations
import djmoney.models.fields


class Migration(migrations.Migration):
    dependencies = [("catalog", "0032_service_shipping_service_shipping_currency")]

    operations = [
        migrations.AlterField(
            model_name="service",
            name="shipping",
            field=djmoney.models.fields.MoneyField(blank=True, decimal_places=2, max_digits=14, null=True, verbose_name="Custo de Frete"),
        ),
    ]
