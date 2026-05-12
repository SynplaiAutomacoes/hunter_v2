from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0017_workorder_delivered_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorder",
            name="unsigned_delivery_reason",
            field=models.TextField(blank=True, verbose_name="Justificativa da entrega sem assinatura"),
        ),
    ]
