from django.db import migrations, models


def normalize_rejected_status_values(apps, schema_editor):
    Budget = apps.get_model("budget", "Budget")
    Budget.objects.filter(status__in=("reprovado", "reproved")).update(status="rejected")


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0044_alter_budget_pdf_observation"),
    ]

    operations = [
        migrations.RunPython(normalize_rejected_status_values, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="budget",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Em Aberto"),
                    ("waiting_client", "Aguardando Relato do Cliente"),
                    ("waiting_diagnosis", "Aguardando Diagnóstico"),
                    ("waiting_items", "Aguardando Itens"),
                    ("waiting_pricing", "Aguardando Precificação"),
                    ("waiting_review", "Aguardando Revisão"),
                    ("waiting_approval", "Aguardando Aprovação"),
                    ("approved", "Aprovado"),
                    ("rejected", "Reprovado"),
                    ("cancelled", "Cancelado"),
                ],
                default="draft",
                max_length=50,
                verbose_name="Status",
            ),
        ),
    ]
