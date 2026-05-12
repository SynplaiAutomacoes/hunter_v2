from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_remove_logincode_unused_fields"),
        ("workorder", "0020_workorder_cancellation_reason_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkOrderHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="Data de Criação")),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="Data de Atualização")),
                ("action", models.CharField(choices=[("reopened", "O.S. reaberta")], max_length=30, verbose_name="Ação")),
                ("reason", models.TextField(blank=True, verbose_name="Justificativa")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="workorder_history_entries", to="accounts.user")),
                ("workorder", models.ForeignKey(on_delete=models.CASCADE, related_name="history_entries", to="workorder.workorder")),
            ],
            options={
                "verbose_name": "Histórico da O.S.",
                "verbose_name_plural": "Histórico das O.S.",
                "ordering": ["-criado_em", "-pk"],
            },
        ),
    ]
