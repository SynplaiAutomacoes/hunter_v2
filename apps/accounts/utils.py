from __future__ import annotations

from django.contrib.auth.models import Permission

from apps.accounts.models import Account, WorkshopRole


DIRECTOR_ROLE_NAME = "Diretor"
COLLABORATOR_ROLE_NAME = "Colaborador"


def get_or_create_director_role(*, account: Account, with_all_permissions: bool = True) -> WorkshopRole:
    role, _ = WorkshopRole.objects.get_or_create(
        account=account,
        name=DIRECTOR_ROLE_NAME,
        defaults={
            "is_system": True,
            "is_editable": False,
        },
    )

    if with_all_permissions:
        role.permissions.set(Permission.objects.all())

    return role


def get_or_create_collaborator_role(*, account: Account) -> WorkshopRole:
    role, _ = WorkshopRole.objects.get_or_create(
        account=account,
        name=COLLABORATOR_ROLE_NAME,
        defaults={
            "is_system": True,
            "is_editable": True,
        },
    )

    return role
