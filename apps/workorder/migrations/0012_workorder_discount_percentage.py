from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workorder", "0011_workorderpaymentmethod_due_date"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=("ALTER TABLE workorder_workorder ADD COLUMN IF NOT EXISTS discount_percentage numeric(7, 6) NOT NULL DEFAULT 0.00"),
                    reverse_sql="ALTER TABLE workorder_workorder DROP COLUMN IF EXISTS discount_percentage",
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="workorder",
                    name="discount_percentage",
                    field=models.DecimalField(
                        decimal_places=6,
                        default=Decimal("0.00"),
                        max_digits=7,
                        validators=[MinValueValidator(0), MaxValueValidator(1)],
                        verbose_name="Desconto da O.S. (%)",
                    ),
                ),
            ],
        ),
    ]
