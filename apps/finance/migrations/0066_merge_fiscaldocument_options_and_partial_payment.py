# Generated manually to join fiscal-document options with the partial-payment merge tip.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0063_alter_fiscaldocument_options_and_more"),
        ("finance", "0065_merge_financial_movement_partial_payment"),
    ]

    operations: list = []
