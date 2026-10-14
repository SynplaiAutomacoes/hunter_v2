from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0075_soft_delete_and_line_overrides"),
    ]

    operations = [
        migrations.AlterField(
            model_name="nfserequest",
            name="consumidor_final",
            field=models.BooleanField(
                blank=True,
                default=None,
                help_text="Indicador de operação de uso ou consumo pessoal (Padrão Nacional). Deixe em branco para não enviar.",
                null=True,
                verbose_name="Consumidor final",
            ),
        ),
    ]
