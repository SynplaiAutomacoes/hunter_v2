# Generated manually to join the feat/nf merge tip with standalone emission support.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0059_merge_feat_nf_and_purchase_return"),
        ("finance", "0060_standalone_emission_support"),
    ]

    operations: list = []
