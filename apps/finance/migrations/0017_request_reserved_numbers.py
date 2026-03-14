from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0016_merge_0014_merge_20260312_0001_0015_bankaccount"),
    ]

    operations = [
        migrations.AddField(
            model_name="nferequest",
            name="reserved_number",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="Número reservado"),
        ),
        migrations.AddField(
            model_name="nferequest",
            name="reserved_series",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="Série reservada"),
        ),
        migrations.AddField(
            model_name="nfserequest",
            name="reserved_rps_number",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="RPS reservado"),
        ),
        migrations.AddField(
            model_name="nfserequest",
            name="reserved_rps_series",
            field=models.CharField(blank=True, default="", max_length=20, verbose_name="Série RPS reservada"),
        ),
    ]
