# Join the financial movement amount index with the purchase-return/transfer merge tip.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0069_financialmovement_fin_mov_ws_amt_idx"),
        ("finance", "0070_merge_purchase_return_ie_and_transfer"),
    ]

    operations: list = []
