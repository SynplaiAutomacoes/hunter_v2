from django.db import migrations


def clear_legacy_consumidor_final_default(apps, schema_editor) -> None:
    NfseRequest = apps.get_model("finance", "NfseRequest")
    NfseRequest.objects.filter(consumidor_final=True).update(consumidor_final=None)


def noop_reverse(apps, schema_editor) -> None:
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0076_nfserequest_consumidor_final_optional"),
    ]

    operations = [
        migrations.RunPython(clear_legacy_consumidor_final_default, noop_reverse),
    ]
