# Generated manually to merge parallel 0084 heads from stripe and staging.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0084_cce_event_sequence_verbose_name"),
        ("finance", "0084_merge_staging_soft_delete_and_ipi_icms"),
    ]

    operations = []
