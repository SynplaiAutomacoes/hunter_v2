# Generated manually for safe oil_type → review_plan FK rename

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("customer", "0019_customer_accepts_messages"),
        ("workshops", "0035_review_plan_and_messaging_updates"),
    ]

    operations = [
        migrations.RenameField(
            model_name="vehicle",
            old_name="oil_type",
            new_name="review_plan",
        ),
        migrations.RenameField(
            model_name="vehicleoilchange",
            old_name="oil_type",
            new_name="review_plan",
        ),
        migrations.AlterField(
            model_name="vehicle",
            name="review_plan",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="vehicles",
                to="workshops.reviewplan",
                verbose_name="Plano de revisão",
            ),
        ),
        migrations.AlterField(
            model_name="vehicleoilchange",
            name="review_plan",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="oil_changes",
                to="workshops.reviewplan",
                verbose_name="Plano de revisão",
            ),
        ),
    ]
