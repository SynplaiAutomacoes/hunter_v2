# Generated manually to join the feat/nf transport leaf with the purchase-return tip.
#
# 0050_merge_20260810_1742 must NOT be a dependency of 0051_nfe_transport_support:
# 0051 was already applied on staging/prod before that merge existed in the graph.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0050_merge_20260810_1742"),
        ("finance", "0058_repair_purchase_return_item_columns"),
    ]

    operations: list = []
