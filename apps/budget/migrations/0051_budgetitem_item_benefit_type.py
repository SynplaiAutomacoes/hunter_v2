from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('budget', '0050_budget_discount_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='budgetitem',
            name='item_benefit_type',
            field=models.CharField(choices=[('normal', 'Normal'), ('warranty', 'Garantia'), ('courtesy', 'Cortesia')], default='normal', max_length=20, verbose_name='Tipo de Benefício'),
        ),
    ]
