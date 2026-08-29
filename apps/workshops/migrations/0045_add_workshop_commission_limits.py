# Generated for Commission v3 — Pool + Limites por Workshop
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('workshops', '0044_outbound_business_weekdays_all_days'),
    ]

    operations = [
        migrations.AddField(
            model_name='workshop',
            name='service_commission_max_percentage',
            field=models.DecimalField(blank=True, decimal_places=6, help_text='Percentual máximo permitido para colaboradores (Serviço). Vazio = sem limite.', max_digits=7, null=True, validators=[MinValueValidator(0), MaxValueValidator(1)], verbose_name='Limite máximo % (Serviço)'),
        ),
        migrations.AddField(
            model_name='workshop',
            name='service_commission_base',
            field=models.CharField(blank=True, choices=[('gross', 'Bruto'), ('profit', 'Lucro')], help_text='Define se a comissão de serviço é sobre valor bruto ou lucro.', max_length=20, null=True, verbose_name='Base (Serviço)'),
        ),
        migrations.AddField(
            model_name='workshop',
            name='product_commission_max_percentage',
            field=models.DecimalField(blank=True, decimal_places=6, help_text='Percentual máximo permitido para colaboradores (Produto). Vazio = sem limite.', max_digits=7, null=True, validators=[MinValueValidator(0), MaxValueValidator(1)], verbose_name='Limite máximo % (Produto)'),
        ),
        migrations.AddField(
            model_name='workshop',
            name='product_commission_base',
            field=models.CharField(blank=True, choices=[('gross', 'Bruto'), ('profit', 'Lucro')], help_text='Define se a comissão de produto é sobre valor bruto ou lucro.', max_length=20, null=True, verbose_name='Base (Produto)'),
        ),
        migrations.AddConstraint(
            model_name='workshop',
            constraint=models.CheckConstraint(condition=models.Q(service_commission_max_percentage__isnull=True) | models.Q(service_commission_max_percentage__gte=0, service_commission_max_percentage__lte=1), name='workshop_service_commission_max_percentage_range'),
        ),
        migrations.AddConstraint(
            model_name='workshop',
            constraint=models.CheckConstraint(condition=models.Q(product_commission_max_percentage__isnull=True) | models.Q(product_commission_max_percentage__gte=0, product_commission_max_percentage__lte=1), name='workshop_product_commission_max_percentage_range'),
        ),
    ]
