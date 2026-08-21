from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0067_alter_budgetitem_description_max_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="budget",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_budgets",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Criado por",
            ),
        ),
    ]
