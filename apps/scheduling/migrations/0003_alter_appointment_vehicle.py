from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("scheduling", "0002_appointment_alert_customer"),
    ]

    operations = [
        migrations.AlterField(
            model_name="appointment",
            name="vehicle",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.PROTECT, related_name="appointments", to="customer.vehicle", verbose_name="Veiculo"),
        ),
    ]
