from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.customer.models import Customer
from apps.messaging.application.services.appointment_alert import sync_appointment_alert_schedule
from apps.messaging.application.services.dispatch_history import apply_dispatch_status_update, cancel_in_flight_dispatch_logs
from apps.messaging.application.services.outbound_dispatch import process_due_outbound_messages
from apps.messaging.application.use_cases.dispatch_message_groups import (
    DispatchGroupsRequest,
    DispatchMessageGroupsUseCase,
)
from apps.messaging.domain.value_objects import DispatchItem
from apps.messaging.models import (
    CustomerMessageGroup,
    CustomerMessageGroupMembership,
    MessageDispatchBatch,
    MessageDispatchLog,
    ScheduledOutboundMessage,
)
from apps.messaging.test_dispatch_message_groups import FakeGroupRepository, FakeQueuePublisher, FakeSegmentBuilder
from apps.scheduling.models import Appointment, AppointmentStatus
from apps.workshops.models.workshops import Workshop


def _workshop(suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Hist {suffix}",
        cnpj=f"11.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


def _customer(workshop: Workshop, suffix: int = 1) -> Customer:
    return Customer.objects.create(
        workshop=workshop,
        name=f"Cliente Hist {suffix}",
        cpf_or_cnpj=f"3905334472{suffix:02d}",
        email=f"hist{suffix}@example.com",
        phone="+5511988887777",
        is_active=True,
    )


class DispatchHistoryUseCaseTests(TestCase):
    def test_dispatch_creates_batch_logs_and_client_message_ids(self) -> None:
        workshop = _workshop(1)
        customer = _customer(workshop, 1)
        group = CustomerMessageGroup.objects.create(
            workshop=workshop,
            name="Grupo Hist",
            message="Ola %%nome%%",
            is_active=True,
        )
        CustomerMessageGroupMembership.objects.create(group=group, customer=customer)
        client_id = str(uuid4())
        publisher = FakeQueuePublisher()
        use_case = DispatchMessageGroupsUseCase(
            group_repo=FakeGroupRepository(groups=[group]),
            segment_builder=FakeSegmentBuilder(customers=[]),
            queue_publisher=publisher,
        )

        result = use_case.execute(
            DispatchGroupsRequest(
                group_id=group.pk,
                client_message_ids={customer.pk: client_id},
                source=MessageDispatchBatch.Source.GROUP_MANUAL,
            )
        )

        self.assertEqual(result.total_customers, 1)
        self.assertEqual(len(result.batch_ids), 1)
        batch = MessageDispatchBatch.objects.get(pk=result.batch_ids[0])
        self.assertEqual(batch.total_count, 1)
        self.assertEqual(batch.queued_count, 1)
        log = MessageDispatchLog.objects.get(batch=batch)
        self.assertEqual(str(log.client_message_id), client_id)
        self.assertEqual(publisher.published[0].client_message_id, client_id)
        self.assertEqual(publisher.published[0].batch_id, batch.pk)


class DispatchStatusUpdateTests(TestCase):
    def test_apply_dispatch_status_update_moves_counters(self) -> None:
        workshop = _workshop(2)
        batch = MessageDispatchBatch.objects.create(
            workshop=workshop,
            source=MessageDispatchBatch.Source.GROUP_MANUAL,
            total_count=1,
            queued_count=1,
            status=MessageDispatchBatch.Status.PROCESSING,
        )
        log = MessageDispatchLog.objects.create(
            batch=batch,
            client_message_id=uuid4(),
            phone="5511999999999",
            message="oi",
            status=MessageDispatchLog.Status.QUEUED,
        )

        updated_log, updated_batch = apply_dispatch_status_update(
            client_message_id=log.client_message_id,
            status="sent",
            batch_id=batch.pk,
        )

        self.assertEqual(updated_log.status, MessageDispatchLog.Status.SENT)
        self.assertEqual(updated_batch.queued_count, 0)
        self.assertEqual(updated_batch.sent_count, 1)
        self.assertEqual(updated_batch.status, MessageDispatchBatch.Status.COMPLETED)

    def test_processing_status_updates_counter_and_rejects_queued_from_worker(self) -> None:
        workshop = _workshop(21)
        batch = MessageDispatchBatch.objects.create(
            workshop=workshop,
            source=MessageDispatchBatch.Source.GROUP_MANUAL,
            total_count=1,
            queued_count=1,
            status=MessageDispatchBatch.Status.QUEUED,
        )
        log = MessageDispatchLog.objects.create(
            batch=batch,
            client_message_id=uuid4(),
            phone="5511999999999",
            message="oi",
            status=MessageDispatchLog.Status.QUEUED,
        )

        with self.assertRaises(ValueError):
            apply_dispatch_status_update(client_message_id=log.client_message_id, status="queued", batch_id=batch.pk)

        updated_log, updated_batch = apply_dispatch_status_update(
            client_message_id=log.client_message_id,
            status="processing",
            batch_id=batch.pk,
        )
        self.assertEqual(updated_log.status, MessageDispatchLog.Status.PROCESSING)
        self.assertEqual(updated_batch.queued_count, 0)
        self.assertEqual(updated_batch.processing_count, 1)
        self.assertEqual(updated_batch.status, MessageDispatchBatch.Status.PROCESSING)


class CancelInFlightDispatchLogsTests(TestCase):
    def test_cancel_marks_queued_and_processing_as_cancelled(self) -> None:
        workshop = _workshop(22)
        batch = MessageDispatchBatch.objects.create(
            workshop=workshop,
            source=MessageDispatchBatch.Source.GROUP_MANUAL,
            total_count=3,
            queued_count=1,
            processing_count=1,
            sent_count=1,
            status=MessageDispatchBatch.Status.PROCESSING,
        )
        queued = MessageDispatchLog.objects.create(
            batch=batch,
            client_message_id=uuid4(),
            phone="5511999999991",
            message="a",
            status=MessageDispatchLog.Status.QUEUED,
        )
        processing = MessageDispatchLog.objects.create(
            batch=batch,
            client_message_id=uuid4(),
            phone="5511999999992",
            message="b",
            status=MessageDispatchLog.Status.PROCESSING,
        )
        sent = MessageDispatchLog.objects.create(
            batch=batch,
            client_message_id=uuid4(),
            phone="5511999999993",
            message="c",
            status=MessageDispatchLog.Status.SENT,
        )

        cancelled = cancel_in_flight_dispatch_logs(workshop_id=workshop.pk)
        queued.refresh_from_db()
        processing.refresh_from_db()
        sent.refresh_from_db()
        batch.refresh_from_db()

        self.assertEqual(cancelled, 2)
        self.assertEqual(queued.status, MessageDispatchLog.Status.CANCELLED)
        self.assertEqual(processing.status, MessageDispatchLog.Status.CANCELLED)
        self.assertEqual(sent.status, MessageDispatchLog.Status.SENT)
        self.assertEqual(batch.queued_count, 0)
        self.assertEqual(batch.processing_count, 0)
        self.assertEqual(batch.cancelled_count, 2)
        self.assertEqual(batch.sent_count, 1)
        self.assertEqual(batch.status, MessageDispatchBatch.Status.CANCELLED)


class AppointmentAlertScheduleTests(TestCase):
    def test_sync_creates_and_cancels_scheduled_outbound(self) -> None:
        workshop = _workshop(3)
        customer = _customer(workshop, 3)
        starts = timezone.now() + timedelta(hours=5)
        appointment = Appointment.objects.create(
            workshop=workshop,
            customer=customer,
            title="Revisao",
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            alert_customer=True,
            alert_lead_time=60,
            status=AppointmentStatus.SCHEDULED,
        )

        scheduled = sync_appointment_alert_schedule(appointment)
        assert scheduled is not None
        self.assertEqual(scheduled.status, ScheduledOutboundMessage.Status.PENDING)
        self.assertEqual(scheduled.run_at, starts - timedelta(minutes=60))

        appointment.alert_customer = False
        appointment.save(update_fields=["alert_customer"])
        self.assertIsNone(sync_appointment_alert_schedule(appointment))
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledOutboundMessage.Status.CANCELLED)


class OutboundTickerTests(TestCase):
    @patch("apps.messaging.application.services.outbound_dispatch.RabbitMQPublisher")
    def test_process_due_outbound_messages_publishes_and_marks_sent(self, publisher_cls: MagicMock) -> None:
        workshop = _workshop(4)
        customer = _customer(workshop, 4)
        publisher = FakeQueuePublisher()
        publisher_cls.return_value = publisher
        row = ScheduledOutboundMessage.objects.create(
            workshop=workshop,
            customer=customer,
            phone="5511999999999",
            message="Lembrete",
            run_at=timezone.now() - timedelta(minutes=1),
            status=ScheduledOutboundMessage.Status.PENDING,
            source=ScheduledOutboundMessage.Source.APPOINTMENT_ALERT,
        )

        result = process_due_outbound_messages(limit=10)
        row.refresh_from_db()

        self.assertEqual(result.claimed, 1)
        self.assertEqual(result.sent, 1)
        self.assertEqual(row.status, ScheduledOutboundMessage.Status.SENT)
        self.assertEqual(len(publisher.published), 1)
        self.assertEqual(publisher.published[0].client_message_id, str(row.client_message_id))


class DispatchWebSocketTokenTests(TestCase):
    def test_issue_and_verify_roundtrip(self) -> None:
        from apps.messaging.application.services.dispatch_ws_auth import (
            DispatchWebSocketAuthError,
            issue_dispatch_ws_token,
            verify_dispatch_ws_token,
        )

        token = issue_dispatch_ws_token(user_id=10, workshop_id=20)
        user_id, workshop_id = verify_dispatch_ws_token(token)
        self.assertEqual(user_id, 10)
        self.assertEqual(workshop_id, 20)

        with self.assertRaises(DispatchWebSocketAuthError):
            verify_dispatch_ws_token("invalid.token.value")

    def test_token_access_requires_membership_and_matching_workshop(self) -> None:
        from apps.accounts.models import User
        from apps.collaborators.models import WorkshopMember
        from apps.messaging.application.services.dispatch_ws_auth import token_can_access_dispatch_batch

        workshop = _workshop(7)
        other = _workshop(8)
        user = User.objects.create_user(username="ws-token-user", password="x")
        WorkshopMember.objects.create(user=user, workshop=workshop)
        batch = MessageDispatchBatch.objects.create(
            workshop=workshop,
            source=MessageDispatchBatch.Source.GROUP_MANUAL,
            total_count=0,
            status=MessageDispatchBatch.Status.COMPLETED,
        )
        other_batch = MessageDispatchBatch.objects.create(
            workshop=other,
            source=MessageDispatchBatch.Source.GROUP_MANUAL,
            total_count=0,
            status=MessageDispatchBatch.Status.COMPLETED,
        )

        self.assertTrue(
            token_can_access_dispatch_batch(
                user_id=user.pk,
                workshop_id=workshop.pk,
                batch_id=batch.pk,
            )
        )
        self.assertFalse(
            token_can_access_dispatch_batch(
                user_id=user.pk,
                workshop_id=workshop.pk,
                batch_id=other_batch.pk,
            )
        )
        outsider = User.objects.create_user(username="ws-outsider", password="x")
        self.assertFalse(
            token_can_access_dispatch_batch(
                user_id=outsider.pk,
                workshop_id=workshop.pk,
                batch_id=batch.pk,
            )
        )


class DispatchStatusIngestViewTests(TestCase):
    @override_settings(MESSAGE_DISPATCH_STATUS_TOKEN="secret-token")
    def test_ingest_requires_token_and_updates_status(self) -> None:
        workshop = _workshop(5)
        batch = MessageDispatchBatch.objects.create(
            workshop=workshop,
            source=MessageDispatchBatch.Source.GROUP_MANUAL,
            total_count=1,
            queued_count=1,
            status=MessageDispatchBatch.Status.PROCESSING,
        )
        log = MessageDispatchLog.objects.create(
            batch=batch,
            client_message_id=uuid4(),
            phone="5511999999999",
            message="oi",
            status=MessageDispatchLog.Status.QUEUED,
        )

        url = reverse("messaging:dispatch_status_ingest")
        unauthorized = self.client.post(
            url,
            data={"client_message_id": str(log.client_message_id), "status": "processing", "batch_id": batch.pk},
            content_type="application/json",
        )
        self.assertEqual(unauthorized.status_code, 401)

        response = self.client.post(
            url,
            data={"client_message_id": str(log.client_message_id), "status": "processing", "batch_id": batch.pk},
            content_type="application/json",
            HTTP_X_DISPATCH_STATUS_TOKEN="secret-token",
        )
        self.assertEqual(response.status_code, 200)
        log.refresh_from_db()
        self.assertEqual(log.status, MessageDispatchLog.Status.PROCESSING)


class WorkerControlTests(SimpleTestCase):
    @override_settings(MESSAGE_WORKER_BASE_URL="")
    def test_stop_skips_when_base_url_missing(self) -> None:
        from apps.messaging.infrastructure.services.worker_control import stop_workshop_dispatch

        self.assertFalse(stop_workshop_dispatch(workshop_id=1))

    @override_settings(MESSAGE_WORKER_BASE_URL="https://worker.example.com")
    @patch("apps.messaging.infrastructure.services.worker_control.requests.post")
    def test_stop_posts_to_stop_path(self, mock_post: MagicMock) -> None:
        from apps.messaging.infrastructure.services.worker_control import stop_workshop_dispatch

        mock_post.return_value = MagicMock(status_code=200, raise_for_status=lambda: None)
        self.assertTrue(stop_workshop_dispatch(workshop_id=42))
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://worker.example.com/stop")
        self.assertEqual(kwargs["json"], {"status": "cancelled", "workshop_id": 42})


class WhatsAppCleanupTests(TestCase):
    @patch("apps.workshops.services.whatsapp_connection_cleanup.stop_workshop_dispatch", return_value=True)
    @patch("apps.workshops.services.whatsapp_connection_cleanup.EvolutionAPIServiceFactory.get_service")
    def test_cleanup_deletes_instance_and_clears_local(self, get_service: MagicMock, stop_dispatch: MagicMock) -> None:
        workshop = _workshop(6)
        workshop.whatsapp_instance_name = "workshop_6"
        workshop.save(update_fields=["whatsapp_instance_name"])
        service = MagicMock()
        get_service.return_value = service

        from apps.workshops.services.whatsapp_connection_cleanup import cleanup_whatsapp_connection

        result = cleanup_whatsapp_connection(workshop=workshop)
        workshop.refresh_from_db()

        self.assertTrue(result.cancelled_worker)
        self.assertTrue(result.deleted_instance)
        self.assertTrue(result.cleared_local)
        self.assertEqual(workshop.whatsapp_instance_name, "")
        service.delete_instance.assert_called_once_with(instance_name="workshop_6")
        stop_dispatch.assert_called_once_with(workshop_id=workshop.pk)


class DispatchItemContractTests(SimpleTestCase):
    def test_dispatch_item_includes_realtime_fields(self) -> None:
        item = DispatchItem(
            workshop_id=1,
            customer_id=2,
            phone="5511999999999",
            message="oi",
            client_message_id="11111111-1111-1111-1111-111111111111",
            group_id=3,
            batch_id=4,
        )
        payload = item.to_dict()
        self.assertEqual(payload["client_message_id"], "11111111-1111-1111-1111-111111111111")
        self.assertEqual(payload["batch_id"], 4)
        self.assertEqual(payload["group_id"], 3)
