from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db.models import Prefetch, QuerySet

from apps.collaborators.models import WorkshopCollaborator, WorkshopMember
from apps.workshops.models.workshops import Workshop

User = get_user_model()

# Campos da pessoa: sincronizados entre os vínculos do mesmo (dono, CPF).
# Exceção: salário e dados da unidade (lotação, comissões, benefícios, folha,
# ativo/inativo por unidade, admissão/saída) permanecem por vínculo.
PERSON_SYNC_FIELDS = [
    "name",
    "cpf",
    "rg",
    "birth_date",
    "sex",
    "phone",
    "email",
    "position",
]


@dataclass(frozen=True)
class WorkshopMembershipInfo:
    workshop_id: int
    workshop_name: str
    role_name: str
    is_active: bool


@dataclass(frozen=True)
class ManagedCollaboratorRow:
    key: str
    pk: int
    name: str
    cpf: str
    user_id: int | None
    system_access: bool
    is_active_any: bool
    position: str
    roles: tuple[str, ...]
    workshops: tuple[WorkshopMembershipInfo, ...]
    has_user: bool


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


def person_key(collaborator: WorkshopCollaborator) -> str:
    """Identidade da pessoa no escopo do dono: (account_id, CPF normalizado).

    CPFs de donos diferentes nunca se misturam (caso Fernando).
    """
    digits = normalize_cpf(getattr(collaborator, "cpf", ""))
    account_id = getattr(getattr(collaborator, "workshop", None), "account_id", None)
    if not digits:
        return f"pk:{collaborator.pk}"
    return f"{account_id}:{digits}"


def members_prefetch(workshop_ids: list[int]) -> Prefetch:
    """Prefetch de TODOS os members do escopo (ativos e inativos, com papel)."""
    return Prefetch(
        "user__workshop_members",
        queryset=WorkshopMember.objects.filter(workshop_id__in=workshop_ids).select_related("workshop", "role"),
        to_attr="all_members",
    )


def members_of(collaborator: WorkshopCollaborator) -> list[WorkshopMember]:
    user = getattr(collaborator, "user", None)
    members = getattr(user, "all_members", None) if user is not None else None
    return list(members) if members else []


def aggregate_collaborators(
    collaborators: list[WorkshopCollaborator],
    *,
    active_workshop_id: int | None = None,
) -> list[ManagedCollaboratorRow]:
    """Uma linha por pessoa (dono, CPF). Vínculos sem CPF caem em linhas próprias."""
    grouped: dict[str, list[WorkshopCollaborator]] = {}
    for collab in collaborators:
        grouped.setdefault(person_key(collab), []).append(collab)

    rows = [_build_row(key, collabs, active_workshop_id=active_workshop_id) for key, collabs in grouped.items()]
    rows.sort(key=lambda r: (r.name or "").lower())
    return rows


def pick_canonical(
    collabs: list[WorkshopCollaborator],
    *,
    active_workshop_id: int | None = None,
) -> WorkshopCollaborator:
    if active_workshop_id is not None:
        for collab in collabs:
            if collab.workshop_id == active_workshop_id:
                return collab
    return max(collabs, key=lambda c: (getattr(c, "atualizado_em", None) is not None, getattr(c, "atualizado_em", None), c.pk or 0))


def _build_row(
    key: str,
    collabs: list[WorkshopCollaborator],
    *,
    active_workshop_id: int | None = None,
) -> ManagedCollaboratorRow:
    canonical = pick_canonical(collabs, active_workshop_id=active_workshop_id)

    all_units: list[tuple[WorkshopCollaborator, WorkshopMembershipInfo]] = []
    for collab in collabs:
        members = [m for m in members_of(collab) if m.workshop_id == collab.workshop_id]
        member = members[0] if members else None
        role_name = str(getattr(getattr(member, "role", None), "name", "") or "").strip()
        all_units.append(
            (
                collab,
                WorkshopMembershipInfo(
                    workshop_id=collab.workshop_id,
                    workshop_name=getattr(collab.workshop, "name", "") or "—",
                    role_name=role_name,
                    is_active=collab.is_active,
                ),
            )
        )

    # Visibilidade: havendo unidade ativa, exibe só as ativas; se inativo em
    # todas, exibe todas (a linha nunca fica sem oficina).
    active_units = [(c, w) for c, w in all_units if c.is_active]
    visible_units = active_units if active_units else all_units

    roles_set: set[str] = set()
    for _, info in visible_units:
        if info.role_name:
            roles_set.add(info.role_name)
    workshops_info = sorted((info for _, info in visible_units), key=lambda w: w.workshop_id)
    return ManagedCollaboratorRow(
        key=key,
        pk=canonical.pk,
        name=canonical.name,
        cpf=canonical.cpf,
        user_id=canonical.user_id,
        system_access=any(c.system_access for c in collabs),
        is_active_any=any(c.is_active for c in collabs),
        position=canonical.position,
        roles=tuple(sorted(roles_set)),
        workshops=tuple(workshops_info),
        has_user=any(c.user_id is not None for c in collabs),
    )


def build_workshops_cell_value(row: ManagedCollaboratorRow, preview_limit: int = 2) -> WorkshopsCellValue:
    items: list[dict[str, str]] = []
    for ws in row.workshops:
        role_label = ws.role_name if ws.role_name else "—"
        status_label = "Ativo" if ws.is_active else "Inativo"
        items.append({"title": ws.workshop_name, "subtitle": f"{role_label} • {status_label}"})

    if not items:
        return WorkshopsCellValue(visible_items=[], hidden_items=[], hidden_count=0)
    return WorkshopsCellValue(
        visible_items=items[:preview_limit],
        hidden_items=items[preview_limit:],
        hidden_count=len(items[preview_limit:]),
    )


def sibling_collaborators(source: WorkshopCollaborator) -> QuerySet[WorkshopCollaborator]:
    """Vínculos-irmãos: mesmo (dono, CPF), excluindo o próprio. Sem CPF, ninguém."""
    digits = normalize_cpf(getattr(source, "cpf", ""))
    workshop = getattr(source, "workshop", None)
    account_id = getattr(workshop, "account_id", None)
    if not digits or account_id is None:
        return WorkshopCollaborator.objects.none()
    # CPF pode estar formatado ou não no banco: compara exato + normalizado em Python.
    candidates = WorkshopCollaborator.objects.filter(workshop__account_id=account_id).exclude(pk=source.pk)
    sibling_ids = [c.pk for c in candidates.only("pk", "cpf") if normalize_cpf(c.cpf) == digits]
    return WorkshopCollaborator.objects.filter(pk__in=sibling_ids)


def sync_personal_fields(source: WorkshopCollaborator, targets: list[WorkshopCollaborator]) -> int:
    """Replica dados da pessoa (nome, cargo etc.) — nunca salário/unidade."""
    synced = 0
    for target in targets:
        if target.pk == source.pk:
            continue
        for field_name in PERSON_SYNC_FIELDS:
            setattr(target, field_name, getattr(source, field_name))
        target.save(update_fields=PERSON_SYNC_FIELDS)
        synced += 1
    return synced


def sync_access(source: WorkshopCollaborator, targets: list[WorkshopCollaborator], role=None) -> int:
    """Replica acesso (flag + papel) para todos os irmãos.

    A flag `system_access` vai para todos (consistência de exibição); member
    e `User.is_active` só para irmãos com login próprio — irmãos sem `user`
    não ganham login implicitamente nem comandam os demais. Logins de
    dono/superuser nunca são desativados por aqui.
    """
    synced = 0
    for target in targets:
        if target.pk == source.pk:
            continue
        if target.system_access != source.system_access:
            target.system_access = source.system_access
            target.save(update_fields=["system_access"])
        if not target.user_id:
            synced += 1
            continue
        target_user = getattr(target, "user", None)
        if target_user is not None and not (target_user.is_superuser or getattr(target_user, "is_account_owner", False)):
            user_active = bool(target.system_access and target.is_active)
            if target_user.is_active != user_active:
                target_user.is_active = user_active
                target_user.save(update_fields=["is_active"])
        if role is not None:
            WorkshopMember.objects.update_or_create(
                user_id=target.user_id,
                workshop=target.workshop,
                defaults={"role": role, "is_active": target.is_active},
            )
        synced += 1
    return synced


def sync_siblings(source: WorkshopCollaborator, role=None, include_access: bool = True) -> int:
    """Sincroniza o vínculo-fonte com todos os irmãos (mesmo dono, mesmo CPF).

    Salário e dados da unidade nunca são tocados aqui (`is_active` do vínculo
    é comandado pelo multiselect via `sync_siblings_workshops`). Sem CPF ou
    sem conta, nada acontece.
    """
    targets = list(sibling_collaborators(source).select_related("user", "workshop"))
    if not targets:
        return 0
    total = sync_personal_fields(source, targets)
    if include_access:
        total += sync_access(source, targets, role=role)
    return total


def sync_siblings_workshops(source: WorkshopCollaborator, selected_workshop_ids: set[int]) -> int:
    """Liga/desliga os vínculos-irmãos conforme o multiselect de oficinas.

    Marcada → vínculo ativo; desmarcada → vínculo inativo. Nunca exclui
    nada; escopo restrito ao mesmo dono + mesmo CPF (irmãos).
    """
    targets = sibling_collaborators(source).select_related("workshop")
    count = 0
    for target in targets:
        should_be_active = target.workshop_id in selected_workshop_ids
        if target.is_active != should_be_active:
            target.is_active = should_be_active
            target.save(update_fields=["is_active"])
            count += 1
    return count
