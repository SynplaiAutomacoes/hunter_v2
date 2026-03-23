from __future__ import annotations

from django.contrib.auth.models import Permission

from apps.accounts.models import Account
from apps.iam.models import WorkshopRole


def get_or_create_director_role(*, account: Account, with_all_permissions: bool = True) -> WorkshopRole:
    role, created = WorkshopRole.objects.get_or_create(
        account=account,
        name="Diretor",
        defaults={
            "is_system": True,
            "is_editable": False,
        },
    )

    if not created:
        # Normaliza flags mesmo em roles existentes (ex.: criadas manualmente antes desta regra)
        update_fields: list[str] = []
        if not role.is_system:
            role.is_system = True
            update_fields.append("is_system")
        if role.is_editable:
            role.is_editable = False
            update_fields.append("is_editable")
        if update_fields:
            role.save(update_fields=update_fields)

    if with_all_permissions:
        role.permissions.set(Permission.objects.all())

    return role
