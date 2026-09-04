# Generated manually to drop orphan fingerprint column on finance_webmaniawebhookevent

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0066_merge_fiscaldocument_options_and_partial_payment"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                DROP INDEX IF EXISTS unique_webmania_webhook_fingerprint;
                DROP INDEX IF EXISTS finance_webmaniawebhookevent_fingerprint_77fa3675;
                DROP INDEX IF EXISTS finance_webmaniawebhookevent_fingerprint_77fa3675_like;
                ALTER TABLE finance_webmaniawebhookevent
                DROP COLUMN IF EXISTS fingerprint;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
