from __future__ import annotations

from django.db import migrations


def grandfather_existing_accounts(apps, schema_editor):
    Account = apps.get_model("accounts", "Account")
    AccountSubscription = apps.get_model("billing", "AccountSubscription")

    existing_account_ids = set(AccountSubscription.objects.values_list("account_id", flat=True))
    to_create = [
        AccountSubscription(
            account_id=account_id,
            plan="full",
            status="grandfathered",
        )
        for account_id in Account.objects.values_list("id", flat=True)
        if account_id not in existing_account_ids
    ]
    if to_create:
        AccountSubscription.objects.bulk_create(to_create, batch_size=500)


def reverse_grandfather(apps, schema_editor):
    AccountSubscription = apps.get_model("billing", "AccountSubscription")
    AccountSubscription.objects.filter(status="grandfathered").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0001_initial_subscription_models"),
        ("accounts", "0009_remove_logincode_unused_fields"),
    ]

    operations = [
        migrations.RunPython(grandfather_existing_accounts, reverse_grandfather),
    ]
