from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workshops", "0014_alter_workshop_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="workshop",
            name="logo",
            field=models.ImageField(blank=True, null=True, upload_to="workshops/logos/", verbose_name="Logo da oficina"),
        ),
    ]
