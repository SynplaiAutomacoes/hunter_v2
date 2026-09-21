# Join the NFS-e consumidor final migration with the staging finance tip.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0070_nfserequest_consumidor_final"),
        ("finance", "0071_merge_amount_index_and_transfer"),
    ]

    operations: list = []
