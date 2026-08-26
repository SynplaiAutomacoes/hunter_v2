# Generated manually to join the Ticket 240 discounts branch with the homol migration tip.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0053_movement_group_discount_fields"),
        ("finance", "0061_merge_feat_nf_and_standalone_emission"),
    ]

    operations: list = []
