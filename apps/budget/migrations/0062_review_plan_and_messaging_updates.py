# Generated manually — remove oil fields from Budget (capture moves to WorkOrder)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("budget", "0061_oil_change_tracking"),
        ("workshops", "0038_review_plan_and_messaging_updates"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="budget",
            name="last_oil_change_date",
        ),
        migrations.RemoveField(
            model_name="budget",
            name="last_oil_change_km",
        ),
        migrations.RemoveField(
            model_name="budget",
            name="oil_type",
        ),
    ]
