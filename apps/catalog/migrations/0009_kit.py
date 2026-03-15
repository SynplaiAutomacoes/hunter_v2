from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("workshops", "0001_initial"),
        ("catalog", "0008_alter_product_image"),
    ]

    operations = [
        migrations.CreateModel(
            name="Kit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255, verbose_name="Kit")),
                ("description", models.TextField(blank=True, verbose_name="Descrição")),
                ("is_active", models.BooleanField(default=True, verbose_name="Ativo")),
                (
                    "workshop",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="kits", to="workshops.workshop"),
                ),
            ],
            options={
                "verbose_name": "Kit",
                "verbose_name_plural": "Kits",
            },
        ),
        migrations.CreateModel(
            name="KitProduct",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                (
                    "kit",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="kit_products", to="catalog.kit"),
                ),
                (
                    "product",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="product_kits", to="catalog.product"),
                ),
            ],
            options={
                "verbose_name": "Item de Kit (Produto)",
                "verbose_name_plural": "Itens de Kit (Produtos)",
            },
        ),
        migrations.CreateModel(
            name="KitService",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                (
                    "kit",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="kit_services", to="catalog.kit"),
                ),
                (
                    "service",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_kits", to="catalog.service"),
                ),
            ],
            options={
                "verbose_name": "Item de Kit (Serviço)",
                "verbose_name_plural": "Itens de Kit (Serviços)",
            },
        ),
        migrations.AddConstraint(
            model_name="kit",
            constraint=models.UniqueConstraint(fields=("workshop", "name"), name="unique_kit_name_per_workshop"),
        ),
        migrations.AddConstraint(
            model_name="kitproduct",
            constraint=models.UniqueConstraint(fields=("kit", "product"), name="unique_product_per_kit"),
        ),
        migrations.AddConstraint(
            model_name="kitservice",
            constraint=models.UniqueConstraint(fields=("kit", "service"), name="unique_service_per_kit"),
        ),
        migrations.AddField(
            model_name="kit",
            name="products",
            field=models.ManyToManyField(blank=True, related_name="kits", through="catalog.KitProduct", to="catalog.product"),
        ),
        migrations.AddField(
            model_name="kit",
            name="services",
            field=models.ManyToManyField(blank=True, related_name="kits", through="catalog.KitService", to="catalog.service"),
        ),
    ]
