from __future__ import annotations

from datetime import datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.customer.models import Customer
from apps.messaging.application.services.appointment_alert import (
    enqueue_appointment_confirmation,
    sync_appointment_alert_schedule,
)
from apps.messaging.application.services.outbound_business_hours import next_outbound_window_start
from apps.messaging.application.services.outbound_dispatch import process_due_outbound_messages
from apps.messaging.models import MessageTemplate, ScheduledOutboundMessage
from apps.messaging.test_dispatch_message_groups import FakeQueuePublisher
from apps.scheduling.models import Appointment, AppointmentStatus
from apps.workshops.models.workshops import Workshop


def _workshop(suffix: int = 1) -> Workshop:
    workshop = Workshop.objects.create(
        name=f"Oficina Guard {suffix}",
        cnpj=f"22.333.444/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Guard, 123",
    )
    workshop.outbound_business_weekdays = "0,1,2,3,4,5,6"
    workshop.outbound_business_start_time = time(8, 0)
    workshop.outbound_business_end_time = time(18, 0)
    workshop.save(
        update_fields=[
            "outbound_business_weekdays",
            "outbound_business_start_time",
            "outbound_business_end_time",
        ]
    )
    return workshop


def _customer(workshop: Workshop, suffix: int = 1) -> Customer:
    return Customer.objects.create(
        workshop=workshop,
        name=f"Cliente Guard {suffix}",
        cpf_or_cnpj=f"3905334473{suffix:02d}",
        email=f"guard{suffix}@example.com",
        phone="+5511988887777",
        is_active=True,
        accepts_messages=True,
    )


def _appointment_template(workshop: Workshop, *, confirmation: bool = False) -> MessageTemplate:
    template_type = MessageTemplate.TemplateType.APPOINTMENT_CONFIRMATION if confirmation else MessageTemplate.TemplateType.APPOINTMENT
    return MessageTemplate.objects.create(
        workshop=workshop,
        name=f"Template {template_type}",
        message="Oi %%primeiro_nome%% em %%data_agendamento%% %%hora_agendamento%%",
        template_type=template_type,
        is_active=True,
    )


class NextOutboundWindowStartTests(SimpleTestCase):
    @override_settings(TIME_ZONE="America/Sao_Paulo")
    def test_returns_moment_when_already_inside_window(self) -> None:
        workshop = SimpleNamespace(
            outbound_business_weekdays="0,1,2,3,4",
            outbound_business_start_time=time(8, 0),
            outbound_business_end_time=time(18, 0),
        )
        moment = datetime(2026, 7, 15, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        self.assertEqual(next_outbound_window_start(workshop, moment), moment)

    @override_settings(TIME_ZONE="America/Sao_Paulo")
    def test_returns_today_open_when_before_window(self) -> None:
        workshop = SimpleNamespace(
            outbound_business_weekdays="0,1,2,3,4",
            outbound_business_start_time=time(8, 0),
            outbound_business_end_time=time(18, 0),
        )
        moment = datetime(2026, 7, 15, 7, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
        expected = datetime(2026, 7, 15, 8, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        self.assertEqual(next_outbound_window_start(workshop, moment), expected)

    @override_settings(TIME_ZONE="America/Sao_Paulo")
    def test_returns_none_when_no_weekdays(self) -> None:
        workshop = SimpleNamespace(
            outbound_business_weekdays="",
            outbound_business_start_time=time(8, 0),
            outbound_business_end_time=time(18, 0),
        )
        moment = datetime(2026, 7, 15, 7, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
        self.assertIsNone(next_outbound_window_start(workshop, moment))


@override_settings(TIME_ZONE="America/Sao_Paulo", OUTBOUND_MAX_DELAY_MINUTES=15)
class OutboundGuardDispatchTests(TestCase):
    @patch("apps.messaging.application.services.outbound_dispatch.RabbitMQPublisher")
    def test_cancels_alert_when_appointment_already_started(self, publisher_cls: MagicMock) -> None:
        workshop = _workshop(1)
        customer = _customer(workshop, 1)
        publisher = FakeQueuePublisher()
        publisher_cls.return_value = publisher
        starts = timezone.now() - timedelta(hours=2)
        appointment = Appointment.objects.create(
            workshop=workshop,
            customer=customer,
            title="Passado",
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            status=AppointmentStatus.SCHEDULED,
            alert_customer=True,
            alert_lead_times=[60],
        )
        row = ScheduledOutboundMessage.objects.create(
            workshop=workshop,
            appointment=appointment,
            customer=customer,
            phone="5511988887777",
            message="Lembrete atrasado",
            run_at=starts - timedelta(minutes=60),
            status=ScheduledOutboundMessage.Status.PENDING,
            source=ScheduledOutboundMessage.Source.APPOINTMENT_ALERT,
        )

        result = process_due_outbound_messages(limit=10, force=True)
        row.refresh_from_db()

        self.assertEqual(result.claimed, 0)
        self.assertEqual(result.sent, 0)
        self.assertEqual(result.cancelled_appointment, 1)
        self.assertEqual(row.status, ScheduledOutboundMessage.Status.CANCELLED)
        self.assertEqual(row.error, "appointment_started")
        self.assertEqual(len(publisher.published), 0)

    @patch("apps.messaging.application.services.outbound_dispatch.RabbitMQPublisher")
    def test_cancels_stale_alert_inside_business_hours(self, publisher_cls: MagicMock) -> None:
        workshop = _workshop(2)
        customer = _customer(workshop, 2)
        publisher = FakeQueuePublisher()
        publisher_cls.return_value = publisher
        fixed_now = datetime(2026, 7, 15, 10, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
        starts = fixed_now + timedelta(hours=2)
        appointment = Appointment.objects.create(
            workshop=workshop,
            customer=customer,
            title="Stale",
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            status=AppointmentStatus.SCHEDULED,
            alert_customer=True,
            alert_lead_times=[60],
        )
        row = ScheduledOutboundMessage.objects.create(
            workshop=workshop,
            appointment=appointment,
            customer=customer,
            phone="5511988887777",
            message="Lembrete stale",
            run_at=fixed_now - timedelta(minutes=20),
            status=ScheduledOutboundMessage.Status.PENDING,
            source=ScheduledOutboundMessage.Source.APPOINTMENT_ALERT,
        )

        with patch("apps.messaging.application.services.outbound_dispatch.timezone.now", return_value=fixed_now):
            result = process_due_outbound_messages(limit=10)
        row.refresh_from_db()

        self.assertEqual(result.claimed, 0)
        self.assertEqual(result.sent, 0)
        self.assertEqual(result.cancelled_stale, 1)
        self.assertEqual(row.status, ScheduledOutboundMessage.Status.CANCELLED)
        self.assertEqual(row.error, "stale")
        self.assertEqual(len(publisher.published), 0)

    @patch("apps.messaging.application.services.outbound_dispatch.RabbitMQPublisher")
    def test_sends_when_window_opens_before_appointment(self, publisher_cls: MagicMock) -> None:
        workshop = _workshop(3)
        customer = _customer(workshop, 3)
        publisher = FakeQueuePublisher()
        publisher_cls.return_value = publisher
        # Wednesday: run_at 07:30, window opens 08:00, appointment 08:30
        fixed_now = datetime(2026, 7, 15, 8, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        starts = datetime(2026, 7, 15, 8, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
        appointment = Appointment.objects.create(
            workshop=workshop,
            customer=customer,
            title="Janela",
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            status=AppointmentStatus.SCHEDULED,
            alert_customer=True,
            alert_lead_times=[60],
        )
        row = ScheduledOutboundMessage.objects.create(
            workshop=workshop,
            appointment=appointment,
            customer=customer,
            phone="5511988887777",
            message="Lembrete janela",
            run_at=datetime(2026, 7, 15, 7, 30, tzinfo=ZoneInfo("America/Sao_Paulo")),
            status=ScheduledOutboundMessage.Status.PENDING,
            source=ScheduledOutboundMessage.Source.APPOINTMENT_ALERT,
        )

        with patch("apps.messaging.application.services.outbound_dispatch.timezone.now", return_value=fixed_now):
            result = process_due_outbound_messages(limit=10)
        row.refresh_from_db()

        self.assertEqual(result.claimed, 1)
        self.assertEqual(result.sent, 1)
        self.assertEqual(result.cancelled_stale, 0)
        self.assertEqual(row.status, ScheduledOutboundMessage.Status.SENT)
        self.assertEqual(len(publisher.published), 1)

    @patch("apps.messaging.application.services.outbound_dispatch.RabbitMQPublisher")
    def test_cancels_alert_for_cancelled_appointment(self, publisher_cls: MagicMock) -> None:
        workshop = _workshop(4)
        customer = _customer(workshop, 4)
        publisher = FakeQueuePublisher()
        publisher_cls.return_value = publisher
        starts = timezone.now() + timedelta(hours=3)
        appointment = Appointment.objects.create(
            workshop=workshop,
            customer=customer,
            title="Cancelado",
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            status=AppointmentStatus.CANCELLED,
            alert_customer=True,
            alert_lead_times=[60],
        )
        row = ScheduledOutboundMessage.objects.create(
            workshop=workshop,
            appointment=appointment,
            customer=customer,
            phone="5511988887777",
            message="Lembrete cancelado",
            run_at=timezone.now() - timedelta(minutes=1),
            status=ScheduledOutboundMessage.Status.PENDING,
            source=ScheduledOutboundMessage.Source.APPOINTMENT_ALERT,
        )

        result = process_due_outbound_messages(limit=10, force=True)
        row.refresh_from_db()

        self.assertEqual(result.claimed, 0)
        self.assertEqual(result.cancelled_appointment, 1)
        self.assertEqual(row.status, ScheduledOutboundMessage.Status.CANCELLED)
        self.assertEqual(row.error, "appointment_not_scheduled")
        self.assertEqual(len(publisher.published), 0)

    @patch("apps.messaging.application.services.outbound_dispatch.RabbitMQPublisher")
    def test_force_does_not_bypass_started_appointment_guard(self, publisher_cls: MagicMock) -> None:
        workshop = _workshop(5)
        customer = _customer(workshop, 5)
        publisher = FakeQueuePublisher()
        publisher_cls.return_value = publisher
        starts = timezone.now() - timedelta(minutes=30)
        appointment = Appointment.objects.create(
            workshop=workshop,
            customer=customer,
            title="Force started",
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            status=AppointmentStatus.SCHEDULED,
            alert_customer=True,
            alert_lead_times=[60],
        )
        row = ScheduledOutboundMessage.objects.create(
            workshop=workshop,
            appointment=appointment,
            customer=customer,
            phone="5511988887777",
            message="Force",
            run_at=starts - timedelta(minutes=60),
            status=ScheduledOutboundMessage.Status.PENDING,
            source=ScheduledOutboundMessage.Source.APPOINTMENT_ALERT,
        )

        result = process_due_outbound_messages(limit=10, force=True)
        row.refresh_from_db()

        self.assertEqual(result.sent, 0)
        self.assertEqual(result.cancelled_appointment, 1)
        self.assertEqual(row.status, ScheduledOutboundMessage.Status.CANCELLED)
        self.assertEqual(len(publisher.published), 0)

    @patch("apps.messaging.application.services.outbound_dispatch.RabbitMQPublisher")
    def test_stale_birthday_alert_still_sends(self, publisher_cls: MagicMock) -> None:
        workshop = _workshop(6)
        customer = _customer(workshop, 6)
        publisher = FakeQueuePublisher()
        publisher_cls.return_value = publisher
        fixed_now = datetime(2026, 7, 15, 10, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
        row = ScheduledOutboundMessage.objects.create(
            workshop=workshop,
            customer=customer,
            phone="5511988887777",
            message="Feliz aniversario",
            run_at=fixed_now - timedelta(hours=3),
            status=ScheduledOutboundMessage.Status.PENDING,
            source=ScheduledOutboundMessage.Source.BIRTHDAY_ALERT,
        )

        with patch("apps.messaging.application.services.outbound_dispatch.timezone.now", return_value=fixed_now):
            result = process_due_outbound_messages(limit=10)
        row.refresh_from_db()

        self.assertEqual(result.claimed, 1)
        self.assertEqual(result.sent, 1)
        self.assertEqual(result.cancelled_stale, 0)
        self.assertEqual(row.status, ScheduledOutboundMessage.Status.SENT)
        self.assertEqual(len(publisher.published), 1)


class AppointmentScheduleGuardTests(TestCase):
    def test_enqueue_confirmation_skips_past_appointment(self) -> None:
        workshop = _workshop(7)
        customer = _customer(workshop, 7)
        _appointment_template(workshop, confirmation=True)
        starts = timezone.now() - timedelta(hours=1)
        appointment = Appointment.objects.create(
            workshop=workshop,
            customer=customer,
            title="Passado confirmacao",
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            status=AppointmentStatus.SCHEDULED,
        )

        self.assertIsNone(enqueue_appointment_confirmation(appointment))
        self.assertFalse(
            ScheduledOutboundMessage.objects.filter(
                appointment=appointment,
                source=ScheduledOutboundMessage.Source.APPOINTMENT_CONFIRMATION,
            ).exists()
        )

    def test_sync_cancels_pending_when_appointment_already_started(self) -> None:
        workshop = _workshop(8)
        customer = _customer(workshop, 8)
        _appointment_template(workshop)
        starts = timezone.now() + timedelta(hours=5)
        appointment = Appointment.objects.create(
            workshop=workshop,
            customer=customer,
            title="Sync passado",
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            status=AppointmentStatus.SCHEDULED,
            alert_customer=True,
            alert_lead_times=[60],
        )
        scheduled = sync_appointment_alert_schedule(appointment)
        self.assertEqual(len(scheduled), 1)

        appointment.starts_at = timezone.now() - timedelta(minutes=5)
        appointment.ends_at = appointment.starts_at + timedelta(hours=1)
        appointment.save(update_fields=["starts_at", "ends_at", "atualizado_em"])

        self.assertEqual(sync_appointment_alert_schedule(appointment), [])
        scheduled[0].refresh_from_db()
        self.assertEqual(scheduled[0].status, ScheduledOutboundMessage.Status.CANCELLED)
