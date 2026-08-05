# Generated manually to resolve conflicting workshops leaf migrations.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("workshops", "0040_alter_workshop_google_review_min_rating"),
        ("workshops", "0041_align_workshop_cost_fields_after_merge"),
    ]

    operations = []
