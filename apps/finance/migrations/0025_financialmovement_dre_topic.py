from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0024_financialmovement_movement_kind_and_workorder_payment"),
    ]

    operations = [
        migrations.AddField(
            model_name="financialmovement",
            name="dre_topic",
            field=models.CharField(
                blank=True,
                choices=[
                    ("receita_bruta_vendas_e_servicos", "Receita Bruta de Vendas e Serviços"),
                    ("custos_mercadorias_vendidas", "Custos Mercadorias Vendidas"),
                    ("receitas_financeiras", "Receitas Financeiras"),
                    ("despesas_financeiras", "Despesas Financeiras"),
                ],
                max_length=50,
                null=True,
                verbose_name="Tópico DRE",
            ),
        ),
    ]
