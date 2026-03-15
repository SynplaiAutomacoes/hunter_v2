from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0022_financialmovement_workorder"),
    ]

    operations = [
        migrations.AddField(
            model_name="financialmovement",
            name="is_paid",
            field=models.BooleanField(default=False, verbose_name="Pago"),
        ),
    ]
