# Generated manually for safe OilType → ReviewPlan rename

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("workshops", "0037_satisfaction_survey_send_immediately_toggle"),
        # Ensure oil_type FKs that still reference workshops.oiltype are created
        # before this RenameModel, otherwise fresh migrate / test DB setup fails.
        ("budget", "0061_oil_change_tracking"),
        ("customer", "0018_oil_change_tracking"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="OilType",
            new_name="ReviewPlan",
        ),
        migrations.AlterModelOptions(
            name="reviewplan",
            options={
                "verbose_name": "Plano de revisão",
                "verbose_name_plural": "Planos de revisão",
            },
        ),
        migrations.RemoveConstraint(
            model_name="reviewplan",
            name="unique_oil_type_name_per_workshop",
        ),
        migrations.AlterField(
            model_name="reviewplan",
            name="workshop",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="review_plans",
                to="workshops.workshop",
            ),
        ),
        migrations.AddField(
            model_name="reviewplan",
            name="repeat_notification",
            field=models.BooleanField(
                default=False,
                help_text="Quando ativo, o aviso do plano de revisão é recalculado e reenviado ao cliente até que uma nova troca seja registrada.",
                verbose_name="Repetir aviso até a troca",
            ),
        ),
        migrations.AddConstraint(
            model_name="reviewplan",
            constraint=models.UniqueConstraint(
                fields=("workshop", "name"),
                name="unique_review_plan_name_per_workshop",
            ),
        ),
    ]
