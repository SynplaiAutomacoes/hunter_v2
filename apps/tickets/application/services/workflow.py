from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from apps.tickets.application.services.attachments import PreparedAttachment, TicketAttachmentError, save_attachments
from apps.tickets.application.services.notifications import TicketNotificationService
from apps.tickets.models import Ticket, TicketAttachmentSource, TicketStatus, TicketStatusHistory
from apps.tickets.permissions import can_act_as_assignee, can_manage_ticket_as_dev, is_developer

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.workshops.models.workshops import Workshop


class TicketWorkflowError(Exception):
    pass


ASSIGNEE_OPERATIONAL_STATUSES: frozenset[str] = frozenset(
    {
        TicketStatus.VALIDACAO_INTERNA,
        TicketStatus.AGUARDANDO_VALIDACAO,
        TicketStatus.REPROVADO,
        TicketStatus.EM_ANDAMENTO,
        TicketStatus.CANCELADO,
    }
)


def _record_history(*, ticket: Ticket, actor: User | None, from_status: str, to_status: str, note: str = "") -> None:
    TicketStatusHistory.objects.create(
        ticket=ticket,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        note=note or "",
    )


class TicketWorkflowService:
    @staticmethod
    @transaction.atomic
    def create_ticket(
        *,
        workshop: Workshop,
        created_by: User,
        title: str,
        problem: str,
        reproduction_steps: str,
        attachments: list[PreparedAttachment] | None = None,
    ) -> Ticket:
        ticket = Ticket.objects.create(
            workshop=workshop,
            created_by=created_by,
            title=title.strip(),
            problem=problem.strip(),
            reproduction_steps=reproduction_steps.strip(),
            status=TicketStatus.ABERTO,
        )
        _record_history(ticket=ticket, actor=created_by, from_status="", to_status=TicketStatus.ABERTO)
        if attachments:
            try:
                save_attachments(ticket=ticket, uploaded_by=created_by, prepared=attachments)
            except TicketAttachmentError as exc:
                raise TicketWorkflowError(str(exc)) from exc
        TicketNotificationService.notify_status_change(ticket=ticket, actor=created_by, new_status=TicketStatus.ABERTO)
        return ticket

    @staticmethod
    @transaction.atomic
    def capture(*, ticket: Ticket, actor: User) -> Ticket:
        if not is_developer(actor):
            raise TicketWorkflowError("Apenas desenvolvedores podem capturar chamados.")
        if ticket.assignee_id is not None:
            raise TicketWorkflowError("Este chamado já possui responsável.")
        if ticket.is_final:
            raise TicketWorkflowError("Não é possível capturar um chamado finalizado.")

        previous = ticket.status
        ticket.assignee = actor
        ticket.status = TicketStatus.EM_ANDAMENTO
        ticket.captured_at = timezone.now()
        ticket.save(update_fields=["assignee", "status", "captured_at", "updated_at"])
        _record_history(ticket=ticket, actor=actor, from_status=previous, to_status=TicketStatus.EM_ANDAMENTO, note="Captura")
        TicketNotificationService.notify_capture(ticket=ticket, actor=actor)
        return ticket

    @staticmethod
    @transaction.atomic
    def reassign(*, ticket: Ticket, actor: User, new_assignee: User) -> Ticket:
        if not can_manage_ticket_as_dev(user=actor):
            raise TicketWorkflowError("Apenas desenvolvedores podem reatribuir chamados.")
        if not is_developer(new_assignee):
            raise TicketWorkflowError("O novo responsável precisa ser um desenvolvedor.")
        if ticket.assignee_id is None:
            raise TicketWorkflowError("Capture o chamado antes de reatribuir.")
        if ticket.is_final:
            raise TicketWorkflowError("Não é possível reatribuir um chamado finalizado.")
        if new_assignee.pk == ticket.assignee_id:
            return ticket

        previous_assignee = ticket.assignee
        ticket.assignee = new_assignee
        ticket.save(update_fields=["assignee", "updated_at"])
        if previous_assignee is not None:
            TicketNotificationService.notify_reassignment(
                ticket=ticket,
                actor=actor,
                previous_assignee=previous_assignee,
            )
        return ticket

    @staticmethod
    @transaction.atomic
    def set_operational_status(*, ticket: Ticket, actor: User, new_status: str, cancellation_reason: str = "") -> Ticket:
        if not can_act_as_assignee(user=actor, ticket=ticket):
            raise TicketWorkflowError("Apenas o responsável pelo chamado pode alterar este status.")
        if ticket.is_final:
            raise TicketWorkflowError("Chamado já finalizado.")
        if new_status not in ASSIGNEE_OPERATIONAL_STATUSES:
            raise TicketWorkflowError("Status inválido para esta ação.")
        if new_status == TicketStatus.FECHADO:
            raise TicketWorkflowError("O status fechado é definido apenas quando o dono aprova a solução.")
        if new_status == TicketStatus.CANCELADO:
            reason = (cancellation_reason or "").strip()
            if not reason:
                raise TicketWorkflowError("Informe o motivo do cancelamento.")
            previous = ticket.status
            ticket.status = TicketStatus.CANCELADO
            ticket.cancellation_reason = reason
            ticket.save(update_fields=["status", "cancellation_reason", "updated_at"])
            _record_history(ticket=ticket, actor=actor, from_status=previous, to_status=TicketStatus.CANCELADO, note=reason)
            TicketNotificationService.notify_status_change(ticket=ticket, actor=actor, new_status=TicketStatus.CANCELADO)
            return ticket

        if new_status == TicketStatus.VALIDACAO_INTERNA and not can_act_as_assignee(user=actor, ticket=ticket):
            raise TicketWorkflowError("Apenas o responsável pode marcar validação interna.")

        previous = ticket.status
        ticket.status = new_status
        ticket.save(update_fields=["status", "updated_at"])
        _record_history(ticket=ticket, actor=actor, from_status=previous, to_status=new_status)
        TicketNotificationService.notify_status_change(ticket=ticket, actor=actor, new_status=new_status)
        return ticket

    @staticmethod
    @transaction.atomic
    def approve_solution(*, ticket: Ticket, actor: User) -> Ticket:
        if ticket.created_by_id != actor.pk:
            raise TicketWorkflowError("Apenas o dono do chamado pode aprovar a solução.")
        if ticket.status != TicketStatus.AGUARDANDO_VALIDACAO:
            raise TicketWorkflowError("O chamado não está aguardando validação.")

        previous = ticket.status
        ticket.status = TicketStatus.FECHADO
        ticket.save(update_fields=["status", "updated_at"])
        _record_history(ticket=ticket, actor=actor, from_status=previous, to_status=TicketStatus.FECHADO, note="Solução aprovada")
        TicketNotificationService.notify_status_change(ticket=ticket, actor=actor, new_status=TicketStatus.FECHADO)
        return ticket

    @staticmethod
    @transaction.atomic
    def reject_solution(
        *,
        ticket: Ticket,
        actor: User,
        reason: str,
        attachments: list[PreparedAttachment] | None = None,
    ) -> Ticket:
        if ticket.created_by_id != actor.pk:
            raise TicketWorkflowError("Apenas o dono do chamado pode rejeitar a solução.")
        if ticket.status != TicketStatus.AGUARDANDO_VALIDACAO:
            raise TicketWorkflowError("O chamado não está aguardando validação.")
        note = (reason or "").strip()
        if not note:
            raise TicketWorkflowError("Informe o motivo da recusa.")

        previous = ticket.status
        ticket.status = TicketStatus.REPROVADO
        ticket.rejection_reason = note
        ticket.save(update_fields=["status", "rejection_reason", "updated_at"])
        _record_history(ticket=ticket, actor=actor, from_status=previous, to_status=TicketStatus.REPROVADO, note=note)

        if attachments:
            tagged = [
                PreparedAttachment(
                    content=item.content,
                    original_name=item.original_name,
                    content_type=item.content_type,
                    size_bytes=item.size_bytes,
                    source=TicketAttachmentSource.REJECTION if item.source == TicketAttachmentSource.UPLOAD else item.source,
                )
                for item in attachments
            ]
            try:
                save_attachments(ticket=ticket, uploaded_by=actor, prepared=tagged)
            except TicketAttachmentError as exc:
                raise TicketWorkflowError(str(exc)) from exc

        TicketNotificationService.notify_status_change(ticket=ticket, actor=actor, new_status=TicketStatus.REPROVADO)
        return ticket

    @staticmethod
    @transaction.atomic
    def add_attachments(*, ticket: Ticket, actor: User, attachments: list[PreparedAttachment]) -> list:
        if ticket.created_by_id != actor.pk and not is_developer(actor):
            raise TicketWorkflowError("Sem permissão para anexar arquivos neste chamado.")
        if ticket.is_final:
            raise TicketWorkflowError("Não é possível anexar arquivos a um chamado finalizado.")
        try:
            return save_attachments(ticket=ticket, uploaded_by=actor, prepared=attachments)
        except TicketAttachmentError as exc:
            raise TicketWorkflowError(str(exc)) from exc
