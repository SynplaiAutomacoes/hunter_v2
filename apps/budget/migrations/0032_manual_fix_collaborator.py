from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ('budget', '0031_merge_20260330_1905'),
        ('collaborators', '0006_workshopcollaborator_timestamps'),
    ]

    operations = [
        migrations.AddField(
            model_name='budget',
            name='collaborator',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='budgets',
                to='collaborators.workshopcollaborator',
                verbose_name='Colaborador'
            ),
        ),
    ]