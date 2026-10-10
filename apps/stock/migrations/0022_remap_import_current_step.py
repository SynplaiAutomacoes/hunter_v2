from django.db import migrations
from django.db.models import F


def remap_import_current_step(apps, schema_editor):
    """Remapeia a etapa salva após a remoção da etapa de seleção do método.

    Antiga etapa 1 (método) foi incorporada à nova etapa 1, então as etapas
    2..N passam a ser 1..N-1. Rascunhos na antiga etapa 1 permanecem na nova
    etapa 1.
    """
    StockImport = apps.get_model("stock", "StockImport")
    StockImport.objects.filter(current_step__gt=1).update(current_step=F("current_step") - 1)


class Migration(migrations.Migration):

    dependencies = [
        ("stock", "0021_alter_stockimport_method"),
    ]

    operations = [
        migrations.RunPython(remap_import_current_step, reverse_code=migrations.RunPython.noop),
    ]
