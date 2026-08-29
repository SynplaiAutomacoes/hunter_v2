# Generated manually to merge leaf nodes:
#   0050_add_warranty_origin
#   0054_merge_excluded_composition_and_os_tip

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0050_add_warranty_origin"),
        ("workorder", "0054_merge_excluded_composition_and_os_tip"),
    ]

    operations: list = []
