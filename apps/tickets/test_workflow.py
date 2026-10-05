from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Account
from apps.collaborators.forms import WorkshopCollaboratorUpdateForm
from apps.collaborators.models import WorkshopCollaborator, WorkshopMember
from apps.iam.models import WorkshopRole
from apps.notifications.models import NotificationRecipient
from apps.tickets.application.services.attachments import attachment_viewer_kind
from apps.tickets.application.services.chat import post_ticket_message
from apps.tickets.application.services.workflow import TicketWorkflowError, TicketWorkflowService
from apps.tickets.application.services.ws_auth import (
    TicketChatWebSocketAuthError,
    issue_ticket_chat_ws_token,
    token_can_access_ticket_chat,
    verify_ticket_chat_ws_token,
)
from apps.tickets.models import Ticket, TicketAttachment, TicketAttachmentSource, TicketStatus
from apps.tickets.permissions import can_access_all_tickets, can_view_ticket, is_developer
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class TicketSupportBaseTestCase(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Tickets")
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Tickets",
            cnpj="11.222.333/0001-81",
            phone="+5511999990001",
            address="Rua A, 1",
        )
        self.owner = User.objects.create_user(username="ticket_owner", password="pass12345", account=self.account)
        self.dev_user = User.objects.create_user(username="ticket_dev", password="pass12345", account=self.account)
        self.dev2_user = User.objects.create_user(username="ticket_dev2", password="pass12345", account=self.account)
        self.other_user = User.objects.create_user(username="ticket_other", password="pass12345", account=self.account)
        self.admin_user = User.objects.create_user(username="sysadmin_tickets", password="pass12345", account=self.account)

        self.role = WorkshopRole.objects.create(account=self.account, name="Colaborador")
        for user in (self.owner, self.dev_user, self.dev2_user, self.other_user, self.admin_user):
            WorkshopMember.objects.create(user=user, workshop=self.workshop, role=self.role, is_active=True)

        self.dev_collab = WorkshopCollaborator.objects.create(
            workshop=self.workshop,
            user=self.dev_user,
            name="Dev Um",
            cpf="39053344705",
            birth_date=date(1990, 1, 1),
            sex=WorkshopCollaborator.Sex.MALE,
            position="Dev",
            salary=Decimal("1000.00"),
            admission_date=date(2020, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.ADMINISTRATIVE,
            system_access=True,
            is_developer=True,
        )
        WorkshopCollaborator.objects.create(
            workshop=self.workshop,
            user=self.dev2_user,
            name="Dev Dois",
            cpf="52998224725",
            birth_date=date(1991, 1, 1),
            sex=WorkshopCollaborator.Sex.MALE,
            position="Dev",
            salary=Decimal("1000.00"),
            admission_date=date(2020, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.ADMINISTRATIVE,
            system_access=True,
            is_developer=True,
        )

    def _login_with_workshop(self, user) -> None:
        self.client.force_login(user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def _create_ticket(self, *, created_by=None) -> Ticket:
        return TicketWorkflowService.create_ticket(
            workshop=self.workshop,
            created_by=created_by or self.owner,
            title="Erro na tela",
            problem="Botão não funciona",
            reproduction_steps="1. Abrir\n2. Clicar",
        )


class TicketWorkflowTests(TicketSupportBaseTestCase):
    def test_create_capture_reassign_preserves_status_and_validation_flow(self) -> None:
        ticket = self._create_ticket()
        self.assertEqual(ticket.status, TicketStatus.ABERTO)

        TicketWorkflowService.capture(ticket=ticket, actor=self.dev_user)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.EM_ANDAMENTO)
        self.assertEqual(ticket.assignee_id, self.dev_user.pk)

        TicketWorkflowService.set_operational_status(
            ticket=ticket,
            actor=self.dev_user,
            new_status=TicketStatus.VALIDACAO_INTERNA,
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.VALIDACAO_INTERNA)

        TicketWorkflowService.reassign(ticket=ticket, actor=self.dev_user, new_assignee=self.dev2_user)
        ticket.refresh_from_db()
        self.assertEqual(ticket.assignee_id, self.dev2_user.pk)
        self.assertEqual(ticket.status, TicketStatus.VALIDACAO_INTERNA)

        TicketWorkflowService.set_operational_status(
            ticket=ticket,
            actor=self.dev2_user,
            new_status=TicketStatus.AGUARDANDO_VALIDACAO,
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.AGUARDANDO_VALIDACAO)

        TicketWorkflowService.reject_solution(ticket=ticket, actor=self.owner, reason="Ainda quebra")
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.REPROVADO)

        TicketWorkflowService.set_operational_status(
            ticket=ticket,
            actor=self.dev2_user,
            new_status=TicketStatus.AGUARDANDO_VALIDACAO,
        )
        TicketWorkflowService.approve_solution(ticket=ticket, actor=self.owner)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.FECHADO)

    def test_cancel_requires_reason_and_owner_cannot_change_status(self) -> None:
        ticket = self._create_ticket()
        TicketWorkflowService.capture(ticket=ticket, actor=self.dev_user)

        with self.assertRaises(TicketWorkflowError):
            TicketWorkflowService.set_operational_status(
                ticket=ticket,
                actor=self.dev_user,
                new_status=TicketStatus.CANCELADO,
                cancellation_reason="",
            )

        with self.assertRaises(TicketWorkflowError):
            TicketWorkflowService.set_operational_status(
                ticket=ticket,
                actor=self.owner,
                new_status=TicketStatus.CANCELADO,
                cancellation_reason="quero cancelar",
            )

        TicketWorkflowService.set_operational_status(
            ticket=ticket,
            actor=self.dev_user,
            new_status=TicketStatus.CANCELADO,
            cancellation_reason="Duplicado",
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.CANCELADO)
        self.assertEqual(ticket.cancellation_reason, "Duplicado")


class TicketCreateViewTests(TicketSupportBaseTestCase):
    def test_create_page_renders_for_authenticated_user(self) -> None:
        self._login_with_workshop(self.owner)
        response = self.client.get(reverse("tickets:create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Abrir chamado")
        self.assertContains(response, "ticket_screen_recorder.js")
        self.assertContains(response, "ticketAttachments(")
        self.assertContains(response, "maxBytes: 314572800")
        self.assertNotContains(response, "maxBytes: 314.572.800")
        self.assertContains(response, "Prepare-se")
        self.assertContains(response, "nova aba")
        self.assertContains(response, "videocam")


class TicketAttachmentViewerTests(TicketSupportBaseTestCase):
    def test_attachment_viewer_kind_detects_video_and_pdf(self) -> None:
        self.assertEqual(attachment_viewer_kind(content_type="video/webm", original_name="gravacao.webm"), "video")
        self.assertEqual(attachment_viewer_kind(content_type="application/octet-stream", original_name="clip.mp4"), "video")
        self.assertEqual(attachment_viewer_kind(content_type="application/pdf", original_name="doc.pdf"), "pdf")
        self.assertEqual(attachment_viewer_kind(content_type="text/plain", original_name="manual.PDF"), "pdf")
        self.assertIsNone(attachment_viewer_kind(content_type="image/png", original_name="foto.png"))

    def test_detail_renders_viewer_controls_for_previewable_attachments(self) -> None:
        ticket = self._create_ticket()
        TicketAttachment.objects.create(
            ticket=ticket,
            uploaded_by=self.owner,
            file_key="tickets/1/1/video.webm",
            content_type="video/webm",
            original_name="gravacao.webm",
            size_bytes=1024,
            source=TicketAttachmentSource.SCREEN_RECORDING,
        )
        TicketAttachment.objects.create(
            ticket=ticket,
            uploaded_by=self.owner,
            file_key="tickets/1/1/doc.pdf",
            content_type="application/pdf",
            original_name="evidencia.pdf",
            size_bytes=2048,
            source=TicketAttachmentSource.UPLOAD,
        )

        self._login_with_workshop(self.owner)
        with patch(
            "apps.tickets.presentation.views.ticket_views.attachment_download_url",
            side_effect=lambda **kwargs: f"https://cdn.example/{kwargs['attachment'].original_name}",
        ):
            response = self.client.get(reverse("tickets:ticket_detail", kwargs={"pk": ticket.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visualizar")
        self.assertContains(response, "open-ticket-attachment-viewer")
        self.assertContains(response, "ticket-attachment-viewer-modal")
        self.assertContains(response, "kind: 'video'")
        self.assertContains(response, "kind: 'pdf'")
        self.assertContains(response, "Baixar")


class TicketDetailActionsPanelTests(TicketSupportBaseTestCase):
    def test_owner_does_not_see_dev_actions_column(self) -> None:
        ticket = self._create_ticket()
        self._login_with_workshop(self.owner)
        response = self.client.get(reverse("tickets:ticket_detail", kwargs={"pk": ticket.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["show_dev_actions"])
        self.assertFalse(response.context["is_developer"])
        self.assertNotContains(response, "Somente desenvolvedores")
        self.assertNotContains(response, "Capturar chamado")

    def test_developer_sees_capture_actions_on_open_ticket(self) -> None:
        ticket = self._create_ticket()
        self._login_with_workshop(self.dev_user)
        response = self.client.get(reverse("tickets:ticket_detail", kwargs={"pk": ticket.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["show_dev_actions"])
        self.assertTrue(response.context["can_capture"])
        self.assertContains(response, "Somente desenvolvedores")
        self.assertContains(response, "Capturar chamado")
        self.assertContains(response, "Assume a responsabilidade")

    def test_assignee_sees_reassign_and_status_sections(self) -> None:
        ticket = self._create_ticket()
        TicketWorkflowService.capture(ticket=ticket, actor=self.dev_user)
        self._login_with_workshop(self.dev_user)
        response = self.client.get(reverse("tickets:ticket_detail", kwargs={"pk": ticket.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["show_dev_actions"])
        self.assertTrue(response.context["can_reassign"])
        self.assertTrue(response.context["can_change_status"])
        self.assertContains(response, "Reatribuir")
        self.assertContains(response, "Alterar status")
        self.assertContains(response, "Novo responsável")
        self.assertContains(response, "Novo status")

    def test_owner_sees_validation_card_outside_dev_column(self) -> None:
        ticket = self._create_ticket()
        TicketWorkflowService.capture(ticket=ticket, actor=self.dev_user)
        TicketWorkflowService.set_operational_status(
            ticket=ticket,
            actor=self.dev_user,
            new_status=TicketStatus.AGUARDANDO_VALIDACAO,
        )
        self._login_with_workshop(self.owner)
        response = self.client.get(reverse("tickets:ticket_detail", kwargs={"pk": ticket.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["show_dev_actions"])
        self.assertTrue(response.context["can_approve_or_reject"])
        self.assertContains(response, "Validar solução")
        self.assertContains(response, "Aprovar solução")
        self.assertContains(response, "Reprovar solução")
        self.assertNotContains(response, "Somente desenvolvedores")


class TicketPermissionTests(TicketSupportBaseTestCase):
    def test_owner_sees_only_own_tickets_and_non_dev_forbidden_on_general(self) -> None:
        own = self._create_ticket()
        other = self._create_ticket(created_by=self.other_user)

        self.assertTrue(can_view_ticket(user=self.owner, ticket=own))
        self.assertFalse(can_view_ticket(user=self.owner, ticket=other))
        self.assertTrue(can_view_ticket(user=self.dev_user, ticket=other))
        self.assertFalse(can_access_all_tickets(self.owner))
        self.assertTrue(is_developer(self.dev_user))

        self._login_with_workshop(self.owner)
        response = self.client.get(reverse("tickets:all_list"))
        self.assertEqual(response.status_code, 403)

        self._login_with_workshop(self.dev_user)
        response = self.client.get(reverse("tickets:all_list"))
        self.assertEqual(response.status_code, 200)

    def test_my_list_multi_status_filter_and_default_non_final(self) -> None:
        open_ticket = self._create_ticket()
        closed_ticket = self._create_ticket()
        Ticket.objects.filter(pk=closed_ticket.pk).update(status=TicketStatus.FECHADO)
        closed_ticket.refresh_from_db()

        self._login_with_workshop(self.owner)

        default_response = self.client.get(reverse("tickets:my_list"))
        self.assertEqual(default_response.status_code, 200)
        default_ids = {ticket.pk for ticket in default_response.context["tickets"]}
        self.assertIn(open_ticket.pk, default_ids)
        self.assertNotIn(closed_ticket.pk, default_ids)

        filtered_response = self.client.get(
            reverse("tickets:my_list"),
            {"status": [TicketStatus.ABERTO, TicketStatus.FECHADO]},
        )
        self.assertEqual(filtered_response.status_code, 200)
        filtered_ids = {ticket.pk for ticket in filtered_response.context["tickets"]}
        self.assertEqual(filtered_ids, {open_ticket.pk, closed_ticket.pk})
        self.assertEqual(
            filtered_response.context["selected_status_values"],
            [TicketStatus.ABERTO, TicketStatus.FECHADO],
        )
        self.assertContains(filtered_response, 'name="status"')
        self.assertContains(filtered_response, 'type="checkbox"')

    def test_all_list_multi_status_filter(self) -> None:
        open_ticket = self._create_ticket()
        closed_ticket = self._create_ticket(created_by=self.other_user)
        Ticket.objects.filter(pk=closed_ticket.pk).update(status=TicketStatus.FECHADO)

        self._login_with_workshop(self.dev_user)
        response = self.client.get(
            reverse("tickets:all_list"),
            {"status": [TicketStatus.FECHADO]},
        )
        self.assertEqual(response.status_code, 200)
        ticket_ids = {ticket.pk for ticket in response.context["tickets"]}
        self.assertIn(closed_ticket.pk, ticket_ids)
        self.assertNotIn(open_ticket.pk, ticket_ids)

    @override_settings(SYSTEM_ADMIN_USERNAMES=["sysadmin_tickets"])
    def test_non_admin_cannot_set_is_developer_flag(self) -> None:
        form = WorkshopCollaboratorUpdateForm(
            instance=self.dev_collab,
            account=self.account,
            workshop=self.workshop,
            request_user=self.owner,
        )
        self.assertNotIn("is_developer", form.fields)

        admin_form = WorkshopCollaboratorUpdateForm(
            instance=self.dev_collab,
            account=self.account,
            workshop=self.workshop,
            request_user=self.admin_user,
        )
        self.assertIn("is_developer", admin_form.fields)


@override_settings(SYSTEM_ADMIN_USERNAMES=["sysadmin_tickets"])
class TicketNotificationTests(TicketSupportBaseTestCase):
    def test_notification_matrix_for_status_capture_and_chat(self) -> None:
        ticket = self._create_ticket()
        self.assertTrue(
            NotificationRecipient.objects.filter(
                user=self.dev_user,
                notification__metadata__event="status_change",
            ).exists()
        )
        self.assertFalse(
            NotificationRecipient.objects.filter(
                user=self.owner,
                notification__metadata__event="status_change",
                notification__message__icontains="Aberto",
            ).exists()
        )

        TicketWorkflowService.capture(ticket=ticket, actor=self.dev_user)
        self.assertTrue(
            NotificationRecipient.objects.filter(
                user=self.owner,
                notification__metadata__event="capture",
            ).exists()
        )

        TicketWorkflowService.set_operational_status(
            ticket=ticket,
            actor=self.dev_user,
            new_status=TicketStatus.AGUARDANDO_VALIDACAO,
        )
        self.assertTrue(
            NotificationRecipient.objects.filter(
                user=self.owner,
                notification__metadata__event="status_change",
                notification__message__icontains="Aguardando validação",
            ).exists()
        )

        with patch("apps.tickets.application.services.chat.broadcast_ticket_message"):
            post_ticket_message(ticket=ticket, author=self.owner, body="Oi dev")
        self.assertTrue(
            NotificationRecipient.objects.filter(
                user=self.dev_user,
                notification__metadata__event="chat_message",
            ).exists()
        )

    def test_owner_who_is_developer_does_not_get_open_ticket_notification(self) -> None:
        WorkshopCollaborator.objects.create(
            workshop=self.workshop,
            user=self.owner,
            name="Owner Dev",
            cpf="11144477735",
            birth_date=date(1992, 1, 1),
            sex=WorkshopCollaborator.Sex.MALE,
            position="Dev",
            salary=Decimal("1000.00"),
            admission_date=date(2020, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.ADMINISTRATIVE,
            system_access=True,
            is_developer=True,
        )
        before = NotificationRecipient.objects.filter(user=self.owner).count()
        ticket = self._create_ticket(created_by=self.owner)
        self.assertEqual(ticket.status, TicketStatus.ABERTO)
        self.assertFalse(
            NotificationRecipient.objects.filter(
                user=self.owner,
                notification__metadata__ticket_id=ticket.pk,
            ).exists()
        )
        self.assertEqual(NotificationRecipient.objects.filter(user=self.owner).count(), before)
        self.assertTrue(
            NotificationRecipient.objects.filter(
                user=self.dev_user,
                notification__metadata__ticket_id=ticket.pk,
                notification__metadata__event="status_change",
            ).exists()
        )

    def test_add_attachments_does_not_notify_anyone(self) -> None:
        from apps.tickets.application.services.attachments import PreparedAttachment

        ticket = self._create_ticket()
        TicketWorkflowService.capture(ticket=ticket, actor=self.dev_user)
        before = NotificationRecipient.objects.count()
        TicketWorkflowService.add_attachments(
            ticket=ticket,
            actor=self.owner,
            attachments=[
                PreparedAttachment(
                    content=b"arquivo",
                    original_name="nota.txt",
                    content_type="text/plain",
                    size_bytes=7,
                    source=TicketAttachmentSource.UPLOAD,
                )
            ],
        )
        self.assertEqual(NotificationRecipient.objects.count(), before)
        TicketWorkflowService.add_attachments(
            ticket=ticket,
            actor=self.dev_user,
            attachments=[
                PreparedAttachment(
                    content=b"devfile",
                    original_name="fix.txt",
                    content_type="text/plain",
                    size_bytes=7,
                    source=TicketAttachmentSource.UPLOAD,
                )
            ],
        )
        self.assertEqual(NotificationRecipient.objects.count(), before)


class TicketWebSocketAuthTests(TicketSupportBaseTestCase):
    def test_ws_token_roundtrip_and_access_checks(self) -> None:
        ticket = self._create_ticket()
        token = issue_ticket_chat_ws_token(user_id=self.owner.pk, ticket_id=ticket.pk)
        user_id, ticket_id = verify_ticket_chat_ws_token(token)
        self.assertEqual(user_id, self.owner.pk)
        self.assertEqual(ticket_id, ticket.pk)
        self.assertTrue(token_can_access_ticket_chat(user_id=self.owner.pk, ticket_id=ticket.pk))
        self.assertFalse(token_can_access_ticket_chat(user_id=self.other_user.pk, ticket_id=ticket.pk))
        self.assertTrue(token_can_access_ticket_chat(user_id=self.dev_user.pk, ticket_id=ticket.pk))

        with self.assertRaises(TicketChatWebSocketAuthError):
            verify_ticket_chat_ws_token("token-invalido")
