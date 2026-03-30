from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0029_drop_legacy_budget_pdf_observation_column"),
    ]

    operations = [
        migrations.AddField(
            model_name="budget",
            name="pdf_observation",
            field=models.CharField(blank=True, default="", max_length=250, verbose_name="Observação do PDF"),
        ),
    ]
