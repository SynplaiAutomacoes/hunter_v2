from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0055_merge_warranty_origin_and_os_tip"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workorderitem",
            name="description",
            field=models.TextField(default="", verbose_name="Descrição"),
        ),
    ]
