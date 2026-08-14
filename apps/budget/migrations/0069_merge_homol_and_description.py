# Generated manually to resolve dual leaves on homol:
# 0067_merge_20260807_1206 (homol numbering merge) and
# 0068_merge_description_and_closed_at (hotfix description + staging closed_at).

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0067_merge_20260807_1206"),
        ("budget", "0068_merge_description_and_closed_at"),
    ]

    operations = []
