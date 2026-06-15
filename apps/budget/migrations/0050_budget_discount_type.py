from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('budget', '0049_add_pricing_method_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='budget',
            name='discount_type',
            field=models.CharField(choices=[('products', 'Apenas Produtos'), ('services', 'Apenas Serviços'), ('both', 'Produtos e Serviços')], default='both', max_length=10, verbose_name='Tipo de Desconto'),
        ),
    ]
