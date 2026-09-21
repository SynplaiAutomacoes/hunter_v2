from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0069_repair_fiscal_document_event_orphan_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="nfserequest",
            name="consumidor_final",
            field=models.BooleanField(
                default=True,
                help_text="Indicador de operação de uso ou consumo pessoal (Padrão Nacional).",
                verbose_name="Consumidor final",
            ),
        ),
    ]
