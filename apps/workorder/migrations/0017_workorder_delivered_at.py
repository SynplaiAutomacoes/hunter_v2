from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0016_workorderpaymentmethod_movement_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorder",
            name="delivered_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Data da Entrega"),
        ),
    ]
