from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.collaborators.models import WorkshopCollaborator
from apps.notifications.domain.services.notification_service import NotificationService
from apps.tickets.constants import DEVELOPER_STATUS_NOTIFICATIONS, OWNER_STATUS_NOTIFICATIONS
from apps.tickets.models import TicketStatus

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.tickets.models import Ticket

User = get_user_model()


def _developer_users() -> list[User]:
    user_ids = WorkshopCollaborator.objects.filter(is_developer=True, is_active=True, user__isnull=False, user__is_active=True).values_list("user_id", flat=True).distinct()
    return list(User.objects.filter(pk__in=user_ids, is_active=True).order_by("username"))


def _ticket_url(ticket: Ticket) -> str:
    return reverse("tickets:ticket_detail", kwargs={"pk": ticket.pk})


def _notify(
    *,
    title: str,
    message: str,
    sender: User | None,
    ticket: Ticket,
    users: list[User],
    event: str,
    exclude_user_ids: set[int] | None = None,
) -> None:
    excluded = exclude_user_ids or set()
    unique_users = {
        user.pk: user
        for user in users
        if user is not None and getattr(user, "pk", None) and int(user.pk) not in excluded
    }.values()
    targets = [(ticket.workshop, user) for user in unique_users]
    if not targets:
        return
    NotificationService.create_notification(
        title=title,
        message=message,
        sender=sender,
        tipo="info",
        targets=targets,
        metadata={
            "ticket_id": ticket.pk,
            "url": _ticket_url(ticket),
            "event": event,
        },
    )


class TicketNotificationService:
    @staticmethod
    def notify_status_change(*, ticket: Ticket, actor: User | None, new_status: str) -> None:
        label = dict(TicketStatus.choices).get(new_status, new_status)
        exclude_user_ids: set[int] = set()
        if actor is not None and getattr(actor, "pk", None):
            exclude_user_ids.add(int(actor.pk))
        # Dono não recebe notificação de "chamado aberto" (mesmo se também for desenvolvedor).
        if new_status == TicketStatus.ABERTO and ticket.created_by_id:
            exclude_user_ids.add(int(ticket.created_by_id))

        if new_status in OWNER_STATUS_NOTIFICATIONS and ticket.created_by_id:
            _notify(
                title=f"Chamado #{ticket.pk} atualizado",
                message=f'Status alterado para "{label}".',
                sender=actor,
                ticket=ticket,
                users=[ticket.created_by],
                event="status_change",
                exclude_user_ids=exclude_user_ids,
            )
        if new_status in DEVELOPER_STATUS_NOTIFICATIONS:
            _notify(
                title=f"Chamado #{ticket.pk} atualizado",
                message=f'Status alterado para "{label}".',
                sender=actor,
                ticket=ticket,
                users=_developer_users(),
                event="status_change",
                exclude_user_ids=exclude_user_ids,
            )

    @staticmethod
    def notify_capture(*, ticket: Ticket, actor: User) -> None:
        _notify(
            title=f"Chamado #{ticket.pk} capturado",
            message=f"{actor.get_username()} assumiu o seu chamado.",
            sender=actor,
            ticket=ticket,
            users=[ticket.created_by],
            event="capture",
            exclude_user_ids={int(actor.pk)},
        )

    @staticmethod
    def notify_reassignment(*, ticket: Ticket, actor: User, previous_assignee: User) -> None:
        _notify(
            title=f"Chamado #{ticket.pk} reatribuído",
            message=f"O chamado foi reatribuído para {ticket.assignee.get_username() if ticket.assignee else 'outro desenvolvedor'}.",
            sender=actor,
            ticket=ticket,
            users=[previous_assignee],
            event="reassignment",
            exclude_user_ids={int(actor.pk)},
        )

    @staticmethod
    def notify_chat_message(*, ticket: Ticket, author: User, body: str) -> None:
        preview = (body or "").strip()
        if len(preview) > 120:
            preview = preview[:117] + "..."

        recipients: list[User] = []
        if ticket.created_by_id == author.pk:
            if ticket.assignee_id:
                recipients = [ticket.assignee]
            else:
                recipients = _developer_users()
        else:
            recipients = [ticket.created_by]

        _notify(
            title=f"Nova mensagem no chamado #{ticket.pk}",
            message=preview or "Nova mensagem no chat.",
            sender=author,
            ticket=ticket,
            users=recipients,
            event="chat_message",
            exclude_user_ids={int(author.pk)},
        )
