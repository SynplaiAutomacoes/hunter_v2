from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("workorder", "0030_workorder_observations"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="workorder",
            name="observations",
        ),
    ]
