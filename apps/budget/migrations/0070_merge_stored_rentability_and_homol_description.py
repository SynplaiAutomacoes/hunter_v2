# Generated manually to resolve dual budget leaves on staging:
# 0068_budget_stored_rentability and 0069_merge_homol_and_description.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0068_budget_stored_rentability"),
        ("budget", "0069_merge_homol_and_description"),
    ]

    operations = []
