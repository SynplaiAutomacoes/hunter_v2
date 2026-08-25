from django.db import migrations
import djmoney.models.fields


class Migration(migrations.Migration):
    dependencies = [("workorder", "0043_workorder_signature_decline_pending")]

    operations = [
        migrations.AlterField(
            model_name="workorderitem",
            name="shipping",
            field=djmoney.models.fields.MoneyField(decimal_places=2, default=0, max_digits=14, verbose_name="Custo de Frete"),
        ),
        migrations.AlterField(
            model_name="workorderitem",
            name="service_shipping",
            field=djmoney.models.fields.MoneyField(decimal_places=2, default=0, max_digits=14, verbose_name="Custo de Frete"),
        ),
    ]
