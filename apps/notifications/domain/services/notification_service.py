from __future__ import annotations

from typing import TYPE_CHECKING, Sequence
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.collaborators.models import WorkshopMember
from apps.notifications.models import Notification, NotificationRecipient

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.workshops.models.workshops import Workshop


class NotificationService:
    @staticmethod
    def create_notification(
        *,
        title: str,
        message: str,
        sender: User | None = None,
        targets: Sequence[tuple[Workshop, User]],
        metadata: dict | None = None,
    ) -> Notification:
        """
        Cria uma notificação e gera NotificationRecipient para os pares (workshop, user).
        """
        metadata = metadata or {}
        with transaction.atomic():
            notification = Notification.objects.create(
                title=title,
                message=message,
                sender=sender,
                metadata=metadata,
            )

            seen_pairs: set[tuple[int, int]] = set()
            recipients: list[NotificationRecipient] = []

            for workshop, user in targets:
                pair = (workshop.pk, user.pk)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    recipients.append(
                        NotificationRecipient(
                            notification=notification,
                            workshop=workshop,
                            user=user,
                        )
                    )

            if recipients:
                NotificationRecipient.objects.bulk_create(recipients)

            return notification

    @classmethod
    def create_system_notification(
        cls,
        *,
        title: str,
        message: str,
        workshop: Workshop,
        sender: User | None = None,
        metadata: dict | None = None,
    ) -> Notification:
        """
        Cria uma notificação do sistema enviada a todos os membros ativos de uma workshop.
        """
        memberships = (
            WorkshopMember.objects.filter(
                workshop=workshop,
                is_active=True,
                user__is_active=True,
            )
            .select_related("user")
            .only("workshop_id", "user")
        )

        targets = [(workshop, member.user) for member in memberships]
        return cls.create_notification(
            title=title,
            message=message,
            sender=sender,
            targets=targets,
            metadata=metadata,
        )

    @staticmethod
    def get_user_notifications(
        *,
        user: User,
        workshop: Workshop,
        limit: int | None = None,
        unread_only: bool = False,
    ) -> QuerySet[NotificationRecipient]:
        """
        Retorna as notificações recebidas pelo usuário na workshop ativa.
        """
        qs = (
            NotificationRecipient.objects.filter(
                user=user,
                workshop=workshop,
            )
            .select_related("notification", "notification__sender", "workshop")
            .order_by("-criado_em")
        )

        if unread_only:
            qs = qs.filter(is_read=False)

        if limit is not None and limit > 0:
            qs = qs[:limit]

        return qs

    @staticmethod
    def mark_as_read(
        *,
        user: User,
        workshop: Workshop,
        notification_ids: Sequence[int],
    ) -> int:
        """
        Marca notificações específicas como lidas.
        """
        now = timezone.now()
        return NotificationRecipient.objects.filter(
            user=user,
            workshop=workshop,
            id__in=notification_ids,
            is_read=False,
        ).update(
            is_read=True,
            read_at=now,
            atualizado_em=now,
        )

    @staticmethod
    def mark_all_as_read(
        *,
        user: User,
        workshop: Workshop,
    ) -> int:
        """
        Marca todas as notificações não lidas da workshop ativa como lidas.
        """
        now = timezone.now()
        return NotificationRecipient.objects.filter(
            user=user,
            workshop=workshop,
            is_read=False,
        ).update(
            is_read=True,
            read_at=now,
            atualizado_em=now,
        )

    @staticmethod
    def delete_notification(
        *,
        user: User,
        notification_id: int,
    ) -> bool:
        """
        Exclui o destinatário de notificação (recipiente) pertencente ao usuário.
        """
        deleted_count, _ = NotificationRecipient.objects.filter(
            id=notification_id,
            user=user,
        ).delete()
        return deleted_count > 0

    @staticmethod
    def get_unread_count(
        *,
        user: User,
        workshop: Workshop,
    ) -> int:
        """
        Retorna a quantidade de notificações não lidas do usuário na workshop ativa.
        """
        return NotificationRecipient.objects.filter(
            user=user,
            workshop=workshop,
            is_read=False,
        ).count()
