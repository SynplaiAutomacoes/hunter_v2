from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from apps.budget.models import Budget
from apps.customer.models import Customer, Vehicle
from apps.customer.services.messaging_consent import customer_can_receive_messages
from apps.messaging.application.services.appointment_alert import sync_appointment_alert_schedule
from apps.messaging.application.services.birthday_alert import enqueue_birthday_alerts_for_day
from apps.messaging.application.services.outbound_dispatch import (
    cancel_pending_outbound_for_customer,
    process_due_outbound_messages,
)
from apps.messaging.application.services.review_plan_alert import sync_review_plan_alert_schedule
from apps.messaging.application.services.satisfaction_survey import schedule_satisfaction_survey_for_workorder
from apps.messaging.application.use_cases.dispatch_message_groups import (
    DispatchGroupsRequest,
    DispatchMessageGroupsUseCase,
)
from apps.messaging.infrastructure.repositories.django_message_group_repository import DjangoMessageGroupRepository
from apps.messaging.infrastructure.services.segment_query_builder import eligible_customers_queryset
from apps.messaging.models import (
    CustomerMessageGroup,
    CustomerMessageGroupMembership,
    MessageTemplate,
    ScheduledOutboundMessage,
)
from apps.messaging.test_dispatch_message_groups import FakeQueuePublisher, FakeSegmentBuilder
from apps.scheduling.models import Appointment, AppointmentStatus
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Consent {suffix}",
        cnpj=f"31.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


def create_customer(*, workshop: Workshop, suffix: int, accepts_messages: bool, birth_date: date | None = None) -> Customer:
    return Customer.objects.create(
        workshop=workshop,
        name=f"Cliente Consent {suffix}",
        cpf_or_cnpj=f"7234567890{suffix:02d}",
        email=f"consent{suffix}@example.com",
        phone="+5511988887777",
        is_active=True,
        accepts_messages=accepts_messages,
        birth_date=birth_date,
    )


class MessagingConsentRuleTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=1)

    def test_new_customer_does_not_accept_messages_by_default(self) -> None:
        customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Padrao",
            cpf_or_cnpj="72345678999",
            email="padrao@example.com",
            phone="+5511988887777",
        )
        self.assertFalse(customer.accepts_messages)
        self.assertFalse(customer_can_receive_messages(customer))

    def test_inactive_customer_cannot_receive_even_when_opted_in(self) -> None:
        customer = create_customer(workshop=self.workshop, suffix=2, accepts_messages=True)
        customer.is_active = False
        self.assertFalse(customer_can_receive_messages(customer))

    def test_missing_customer_cannot_receive(self) -> None:
        self.assertFalse(customer_can_receive_messages(None))


class GroupRecipientConsentTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=2)
        self.opted_in = create_customer(workshop=self.workshop, suffix=3, accepts_messages=True)
        self.opted_out = create_customer(workshop=self.workshop, suffix=4, accepts_messages=False)

    def test_eligible_queryset_excludes_opted_out_customer(self) -> None:
        eligible = eligible_customers_queryset(workshop=self.workshop)
        self.assertIn(self.opted_in, eligible)
        self.assertNotIn(self.opted_out, eligible)

    def test_group_members_exclude_opted_out_customer(self) -> None:
        group = CustomerMessageGroup.objects.create(
            workshop=self.workshop,
            name="Grupo Consent",
            message="Ola %%nome%%",
            is_active=True,
        )
        CustomerMessageGroupMembership.objects.create(group=group, customer=self.opted_in)
        CustomerMessageGroupMembership.objects.create(group=group, customer=self.opted_out)

        members = DjangoMessageGroupRepository().get_group_members(group)
        self.assertEqual([member.pk for member in members], [self.opted_in.pk])

    def test_dispatch_publishes_only_for_opted_in_customer(self) -> None:
        group = CustomerMessageGroup.objects.create(
            workshop=self.workshop,
            name="Grupo Disparo Consent",
            message="Ola %%nome%%",
            is_active=True,
        )
        CustomerMessageGroupMembership.objects.create(group=group, customer=self.opted_in)
        CustomerMessageGroupMembership.objects.create(group=group, customer=self.opted_out)

        publisher = FakeQueuePublisher()
        use_case = DispatchMessageGroupsUseCase(
            group_repo=DjangoMessageGroupRepository(),
            segment_builder=FakeSegmentBuilder(customers=[]),
            queue_publisher=publisher,
        )
        result = use_case.execute(DispatchGroupsRequest(workshop_id=self.workshop.pk))

        self.assertEqual(result.total_customers, 1)
        self.assertEqual([item.customer_id for item in publisher.published], [self.opted_in.pk])


class AlertSchedulingConsentTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=3)
        self.customer = create_customer(workshop=self.workshop, suffix=5, accepts_messages=False)
        self.vehicle = Vehicle.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            plate="CON1S23",
            brand="VW",
            model="Gol",
            year_fabrication="2018",
            year_model="2019",
            color="Prata",
            next_oil_change_date=timezone.localdate() + timedelta(days=10),
        )
        MessageTemplate.objects.create(
            workshop=self.workshop,
            name="Revisao Consent",
            message="Troca %%placa%%",
            template_type=MessageTemplate.TemplateType.REVIEW_PLAN,
            is_active=True,
        )
        MessageTemplate.objects.create(
            workshop=self.workshop,
            name="Agenda Consent",
            message="Oi %%nome%% em %%data_agendamento%%",
            template_type=MessageTemplate.TemplateType.APPOINTMENT,
            is_active=True,
        )

    def _create_appointment(self, *, customer: Customer | None, guest_phone: str = "") -> Appointment:
        starts = timezone.now() + timedelta(days=2)
        return Appointment.objects.create(
            workshop=self.workshop,
            customer=customer,
            guest_customer_name="Convidado" if customer is None else "",
            guest_customer_phone=guest_phone,
            title="Revisao",
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            status=AppointmentStatus.SCHEDULED,
            alert_customer=True,
            alert_lead_times=[60],
        )

    def test_review_plan_alert_is_not_scheduled_for_opted_out_customer(self) -> None:
        with patch(
            "apps.messaging.application.services.review_plan_alert.notification_run_at_for_vehicle",
            return_value=timezone.now() + timedelta(days=1),
        ):
            scheduled = sync_review_plan_alert_schedule(self.vehicle)
        self.assertIsNone(scheduled)
        self.assertFalse(ScheduledOutboundMessage.objects.filter(vehicle=self.vehicle).exists())

    def test_review_plan_alert_cancels_pending_when_customer_opts_out(self) -> None:
        self.customer.accepts_messages = True
        self.customer.save(update_fields=["accepts_messages"])
        with patch(
            "apps.messaging.application.services.review_plan_alert.notification_run_at_for_vehicle",
            return_value=timezone.now() + timedelta(days=1),
        ):
            scheduled = sync_review_plan_alert_schedule(self.vehicle)
        assert scheduled is not None

        self.customer.accepts_messages = False
        self.customer.save(update_fields=["accepts_messages"])
        self.vehicle.refresh_from_db()
        with patch(
            "apps.messaging.application.services.review_plan_alert.notification_run_at_for_vehicle",
            return_value=timezone.now() + timedelta(days=1),
        ):
            self.assertIsNone(sync_review_plan_alert_schedule(self.vehicle))

        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledOutboundMessage.Status.CANCELLED)

    def test_appointment_alert_is_not_scheduled_for_opted_out_customer(self) -> None:
        appointment = self._create_appointment(customer=self.customer)
        self.assertEqual(sync_appointment_alert_schedule(appointment), [])
        self.assertFalse(ScheduledOutboundMessage.objects.filter(appointment=appointment).exists())

    def test_appointment_alert_still_schedules_for_guest_without_customer(self) -> None:
        appointment = self._create_appointment(customer=None, guest_phone="+5511989472983")
        scheduled = sync_appointment_alert_schedule(appointment)
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0].phone, "5511989472983")

    def test_birthday_alert_skips_opted_out_customer(self) -> None:
        today = timezone.localdate()
        MessageTemplate.objects.create(
            workshop=self.workshop,
            name="Niver Consent",
            message="Feliz aniversario %%nome%%",
            template_type=MessageTemplate.TemplateType.BIRTHDAY,
            is_active=True,
        )
        create_customer(workshop=self.workshop, suffix=6, accepts_messages=False, birth_date=date(1990, today.month, today.day))
        opted_in = create_customer(workshop=self.workshop, suffix=7, accepts_messages=True, birth_date=date(1990, today.month, today.day))

        created = enqueue_birthday_alerts_for_day()

        self.assertEqual(created, 1)
        rows = ScheduledOutboundMessage.objects.filter(source=ScheduledOutboundMessage.Source.BIRTHDAY_ALERT)
        self.assertEqual([row.customer_id for row in rows], [opted_in.pk])


class SatisfactionSurveyConsentTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=4)
        self.workshop.satisfaction_survey_enabled = True
        self.workshop.save(update_fields=["satisfaction_survey_enabled"])
        self.customer = create_customer(workshop=self.workshop, suffix=8, accepts_messages=False)
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            entry_date=timezone.localdate(),
        )
        self.workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            status=WorkOrderStatus.APPROVED,
            delivered_at=timezone.now(),
        )
        MessageTemplate.objects.create(
            workshop=self.workshop,
            name="Avaliacao Consent",
            message="Oi %%nome%% da %%nome_fantasia%%. Avalie: %%link-avaliacao%%",
            template_type=MessageTemplate.TemplateType.SATISFACTION,
            is_active=True,
        )

    def test_survey_is_not_scheduled_for_opted_out_customer(self) -> None:
        self.assertIsNone(schedule_satisfaction_survey_for_workorder(self.workorder))
        self.assertFalse(ScheduledOutboundMessage.objects.exists())


class OutboundDispatchConsentTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=5)

    def _create_pending(self, customer: Customer) -> ScheduledOutboundMessage:
        return ScheduledOutboundMessage.objects.create(
            workshop=self.workshop,
            customer=customer,
            phone="5511999999999",
            message="Lembrete",
            run_at=timezone.now() - timedelta(minutes=1),
            status=ScheduledOutboundMessage.Status.PENDING,
            source=ScheduledOutboundMessage.Source.APPOINTMENT_ALERT,
        )

    @patch("apps.messaging.application.services.outbound_dispatch.RabbitMQPublisher")
    def test_due_message_of_opted_out_customer_is_cancelled_and_not_published(self, publisher_cls: MagicMock) -> None:
        publisher = FakeQueuePublisher()
        publisher_cls.return_value = publisher
        row = self._create_pending(create_customer(workshop=self.workshop, suffix=9, accepts_messages=False))

        result = process_due_outbound_messages(limit=10, force=True)

        row.refresh_from_db()
        self.assertEqual(row.status, ScheduledOutboundMessage.Status.CANCELLED)
        self.assertEqual(result.claimed, 0)
        self.assertEqual(result.sent, 0)
        self.assertEqual(publisher.published, [])

    @patch("apps.messaging.application.services.outbound_dispatch.RabbitMQPublisher")
    def test_due_message_of_opted_in_customer_is_published(self, publisher_cls: MagicMock) -> None:
        publisher = FakeQueuePublisher()
        publisher_cls.return_value = publisher
        row = self._create_pending(create_customer(workshop=self.workshop, suffix=10, accepts_messages=True))

        result = process_due_outbound_messages(limit=10, force=True)

        row.refresh_from_db()
        self.assertEqual(row.status, ScheduledOutboundMessage.Status.SENT)
        self.assertEqual(result.sent, 1)
        self.assertEqual(len(publisher.published), 1)

    def test_cancel_pending_outbound_for_customer_only_touches_pending_rows(self) -> None:
        customer = create_customer(workshop=self.workshop, suffix=11, accepts_messages=True)
        pending = self._create_pending(customer)
        sent = self._create_pending(customer)
        sent.status = ScheduledOutboundMessage.Status.SENT
        sent.save(update_fields=["status"])

        cancelled = cancel_pending_outbound_for_customer(customer.pk)

        pending.refresh_from_db()
        sent.refresh_from_db()
        self.assertEqual(cancelled, 1)
        self.assertEqual(pending.status, ScheduledOutboundMessage.Status.CANCELLED)
        self.assertEqual(sent.status, ScheduledOutboundMessage.Status.SENT)
