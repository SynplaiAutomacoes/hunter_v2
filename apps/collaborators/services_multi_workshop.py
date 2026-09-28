from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db.models import QuerySet

from apps.collaborators.models import WorkshopCollaborator, WorkshopMember
from apps.workshops.models.workshops import Workshop

User = get_user_model()


@dataclass(frozen=True)
class WorkshopsCellValue:
    visible_items: list[dict[str, str]]
    hidden_items: list[dict[str, str]]
    hidden_count: int
    empty_label: str = "Sem oficina vinculada"


def normalize_cpf(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def owner_account_for(user: User, active_workshop: Workshop | None):
    """Resolve a conta dona a partir da oficina ativa (fallback: conta do usuário)."""
    account = getattr(active_workshop, "account", None)
    if account is not None:
        return account
    return getattr(user, "account", None)


def owner_workshops_queryset(user: User, active_workshop: Workshop | None) -> QuerySet[Workshop]:
    """Oficinas-irmãs da conta dona (QuerySet, para uso em forms e filtros).

    Não filtra por diretor aqui: o gate de diretor vive no dispatch da view.
    """
    account = owner_account_for(user, active_workshop)
    if account is None or getattr(account, "pk", None) is None:
        return Workshop.objects.none()
    return Workshop.objects.filter(account_id=account.pk, is_active=True).order_by("name")


def resolve_owner_workshops(user: User, active_workshop: Workshop | None) -> list[Workshop]:
    return list(owner_workshops_queryset(user, active_workshop).select_related("account"))


def member_for_collaborator(collaborator: WorkshopCollaborator) -> WorkshopMember | None:
    """Member do vínculo a partir do prefetch `user__workshop_members → all_members`."""
    user = getattr(collaborator, "user", None)
    members = getattr(user, "all_members", None) if user is not None else None
    if not members:
        return None
    for member in members:
        if member.workshop_id == collaborator.workshop_id:
            return member
    return None


def build_single_workshop_cell_value(collaborator: WorkshopCollaborator) -> WorkshopsCellValue:
    """Célula 'Oficinas' para a lista gerenciar: um item por vínculo (sem agregação)."""
    workshop = getattr(collaborator, "workshop", None)
    member = member_for_collaborator(collaborator)
    role_name = str(getattr(getattr(member, "role", None), "name", "") or "").strip()
    status_label = "Ativo" if collaborator.is_active else "Inativo"
    return WorkshopsCellValue(
        visible_items=[
            {
                "title": getattr(workshop, "name", "") or "—",
                "subtitle": f"{role_name or '—'} • {status_label}",
            }
        ],
        hidden_items=[],
        hidden_count=0,
    )
