from django.core.validators import FileExtensionValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workshops", "0015_workshop_logo"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workshop",
            name="logo",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="workshops/logos/",
                validators=[FileExtensionValidator(allowed_extensions=["png", "jpg", "jpeg", "gif", "webp", "svg"])],
                verbose_name="Logo da oficina",
            ),
        ),
    ]
