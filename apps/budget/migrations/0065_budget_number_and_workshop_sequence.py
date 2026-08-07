from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion
from django.db.models import F, Max


def backfill_budget_numbers_and_sequences(apps, schema_editor) -> None:
    Budget = apps.get_model("budget", "Budget")
    WorkshopBudgetSequence = apps.get_model("budget", "WorkshopBudgetSequence")
    Workshop = apps.get_model("workshops", "Workshop")

    Budget.objects.all().update(number=F("id"))

    workshop_ids = set(Workshop.objects.values_list("pk", flat=True))
    budget_workshop_ids = set(Budget.objects.values_list("workshop_id", flat=True).distinct())
    all_workshop_ids = workshop_ids | {wid for wid in budget_workshop_ids if wid is not None}

    for workshop_id in all_workshop_ids:
        qs = Budget.objects.filter(workshop_id=workshop_id)
        has_number_one = qs.filter(number=1).exists()
        if has_number_one:
            last_number = qs.aggregate(max_number=Max("number"))["max_number"] or 0
        else:
            last_number = 0
        WorkshopBudgetSequence.objects.update_or_create(
            workshop_id=workshop_id,
            defaults={"last_number": int(last_number)},
        )


def noop_reverse(apps, schema_editor) -> None:
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("budget", "0064_backfill_budget_first_approved_at"),
        ("workshops", "0044_outbound_business_weekdays_all_days"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkshopBudgetSequence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("last_number", models.PositiveIntegerField(default=0, verbose_name="Último número alocado")),
                (
                    "workshop",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="budget_sequence",
                        to="workshops.workshop",
                        verbose_name="Oficina",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sequência de orçamento da oficina",
                "verbose_name_plural": "Sequências de orçamento das oficinas",
            },
        ),
        migrations.AddField(
            model_name="budget",
            name="number",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="Número"),
        ),
        migrations.RunPython(backfill_budget_numbers_and_sequences, noop_reverse),
        migrations.AlterField(
            model_name="budget",
            name="number",
            field=models.PositiveIntegerField(verbose_name="Número"),
        ),
        migrations.AddConstraint(
            model_name="budget",
            constraint=models.UniqueConstraint(fields=("workshop", "number"), name="unique_budget_number_per_workshop"),
        ),
    ]
