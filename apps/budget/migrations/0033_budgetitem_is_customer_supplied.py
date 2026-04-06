from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0032_manual_fix_collaborator"),
    ]

    operations = [
        migrations.AddField(
            model_name="budgetitem",
            name="is_customer_supplied",
            field=models.BooleanField(default=False, verbose_name="Peça trazida pelo cliente"),
        ),
    ]
