import django.db.models.deletion
from django.db import migrations, models

from . import _idempotent


class Migration(migrations.Migration):
    dependencies = [
        ("collaborators", "0017_backfill_payroll_commission_titles"),
        ("workorder", "0046_leftover_courtesy_reason_default"),
    ]

    operations = [
        _idempotent.AddFieldIfMissing(
            model_name="workorder",
            name="previous_mechanic",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="collaborators.workshopcollaborator",
                verbose_name="Mecânico responsável pelo serviço anterior",
            ),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="workorder",
            name="courtesy_reason_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("part_defect", "Defeito de peça"),
                    ("labor_failure", "Falha de mão de obra"),
                    ("both", "Ambos"),
                ],
                max_length=20,
                null=True,
                verbose_name="Motivo da cortesia/garantia",
            ),
        ),
        _idempotent.AddFieldIfMissing(
            model_name="workorder",
            name="courtesy_reason_description",
            field=models.TextField(blank=True, verbose_name="Descrição do motivo da cortesia/garantia"),
        ),
    ]
