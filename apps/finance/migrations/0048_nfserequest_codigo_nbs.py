from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0047_backfill_workorder_financial_descriptions"),
    ]

    operations = [
        migrations.AddField(
            model_name="nfserequest",
            name="codigo_nbs",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Código NBS da NFS-e (Padrão Nacional: 9 dígitos).",
                max_length=9,
                verbose_name="Código NBS",
            ),
        ),
    ]
