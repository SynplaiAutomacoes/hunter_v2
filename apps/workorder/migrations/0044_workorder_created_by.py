from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0043_workorder_signature_decline_pending"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorder",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_workorders",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Criado por",
            ),
        ),
    ]
