from django.db import migrations, models


def backfill_stored_rentability(apps, schema_editor) -> None:
    from apps.budget.models import Budget

    last_pk = 0
    while True:
        batch = list(Budget.objects.filter(pk__gt=last_pk).select_related("workshop").order_by("pk")[:100])
        if not batch:
            break
        for budget in batch:
            try:
                budget.refresh_stored_rentability()
            except Exception:
                continue
        last_pk = batch[-1].pk


def noop_reverse(apps, schema_editor) -> None:
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0067_alter_budgetitem_description_max_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="budget",
            name="stored_rentability",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Rentabilidade do PDF do gestor, persistida no write path para não recalcular em listagens.",
                max_digits=7,
                null=True,
                verbose_name="Rentabilidade armazenada",
            ),
        ),
        migrations.RunPython(backfill_stored_rentability, noop_reverse),
    ]
