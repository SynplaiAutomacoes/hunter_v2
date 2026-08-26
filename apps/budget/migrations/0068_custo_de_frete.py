from django.db import migrations
import djmoney.models.fields


class Migration(migrations.Migration):
    dependencies = [("budget", "0067_alter_budgetitem_description_max_length")]

    operations = [
        migrations.AlterField(
            model_name="budgetitem",
            name="shipping",
            field=djmoney.models.fields.MoneyField(decimal_places=2, default=0, max_digits=14, verbose_name="Custo de Frete"),
        ),
        migrations.AlterField(
            model_name="budgetitem",
            name="service_shipping",
            field=djmoney.models.fields.MoneyField(decimal_places=2, default=0, max_digits=14, verbose_name="Custo de Frete"),
        ),
    ]
