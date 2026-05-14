from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workshops", "0022_enable_unaccent_extension"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkshopCostHoliday",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(verbose_name="Data do feriado")),
                ("description", models.CharField(blank=True, max_length=120, verbose_name="Descricao")),
                (
                    "workshop_cost",
                    models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="holidays", to="workshops.workshopcost"),
                ),
            ],
            options={
                "verbose_name": "Feriado do Custo da Oficina",
                "verbose_name_plural": "Feriados do Custo da Oficina",
                "ordering": ["date", "pk"],
            },
        ),
        migrations.AddConstraint(
            model_name="workshopcostholiday",
            constraint=models.UniqueConstraint(fields=("workshop_cost", "date"), name="unique_workshop_cost_holiday_date"),
        ),
    ]
