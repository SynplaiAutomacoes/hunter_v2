from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings

from apps.collaborators.models import WorkshopCollaborator

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.tickets.models import Ticket


def is_system_admin(user: User | None) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    admin_usernames = getattr(settings, "SYSTEM_ADMIN_USERNAMES", []) or []
    return user.username in admin_usernames


def is_developer(user: User | None) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return WorkshopCollaborator.objects.filter(
        user=user,
        is_developer=True,
        is_active=True,
    ).exists()


def can_access_all_tickets(user: User | None) -> bool:
    return is_system_admin(user) or is_developer(user)


def can_view_ticket(*, user: User | None, ticket: Ticket) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if ticket.created_by_id == user.pk:
        return True
    return can_access_all_tickets(user)


def can_manage_ticket_as_dev(*, user: User | None, ticket: Ticket | None = None) -> bool:
    """Developer actions (capture, reassign, operational status). SYSTEM_ADMIN alone is not enough."""
    return is_developer(user)


def can_act_as_assignee(*, user: User | None, ticket: Ticket) -> bool:
    if not can_manage_ticket_as_dev(user=user):
        return False
    return ticket.assignee_id is not None and ticket.assignee_id == getattr(user, "pk", None)
