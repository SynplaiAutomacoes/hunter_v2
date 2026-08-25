# Keeps the historical migration identifier while joining the NBS branch.
# The former second dependency was never shipped, preventing the entire
# finance migration graph from loading.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0048_nfserequest_codigo_nbs"),
    ]

    operations = []
