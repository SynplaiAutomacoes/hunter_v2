from __future__ import annotations

from django.contrib.auth.models import Permission

from apps.accounts.models import Account
from apps.iam.models import WorkshopRole


def get_or_create_director_role(*, account: Account, with_all_permissions: bool = True) -> WorkshopRole:
    role, _ = WorkshopRole.objects.get_or_create(
        account=account,
        name="Diretor",
        defaults={
            "is_system": True,
            "is_editable": False,
        },
    )

    if with_all_permissions:
        role.permissions.set(Permission.objects.all())

    return role
