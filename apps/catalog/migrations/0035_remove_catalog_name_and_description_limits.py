from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0034_backfill_product_cost_from_imports"),
    ]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="name",
            field=models.TextField(verbose_name="Produto"),
        ),
        migrations.AlterField(
            model_name="product",
            name="description",
            field=models.TextField(blank=True, verbose_name="Descrição"),
        ),
        migrations.AlterField(
            model_name="service",
            name="name",
            field=models.TextField(verbose_name="Serviço"),
        ),
        migrations.AlterField(
            model_name="kit",
            name="name",
            field=models.TextField(verbose_name="Kit"),
        ),
    ]
