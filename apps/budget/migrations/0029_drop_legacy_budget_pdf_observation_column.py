from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("budget", "0027_budget_discount_percentage"),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE budget_budget DROP COLUMN IF EXISTS pdf_observation;",
            reverse_sql=("ALTER TABLE budget_budget ADD COLUMN IF NOT EXISTS pdf_observation varchar(250) NOT NULL DEFAULT '';"),
        ),
    ]
