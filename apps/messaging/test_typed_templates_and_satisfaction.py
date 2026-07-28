from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from apps.budget.models import Budget
from apps.customer.models import Customer, Vehicle
from apps.messaging.application.services.appointment_alert import sync_appointment_alert_schedule
from apps.messaging.application.services.birthday_alert import enqueue_birthday_alerts_for_day
from apps.messaging.application.services.oil_change_alert import sync_oil_change_alert_schedule
from apps.messaging.application.services.satisfaction_survey import (
    SATISFACTION_SURVEY_MESSAGE,
    schedule_satisfaction_survey_for_workorder,
)
from apps.messaging.infrastructure.forms.message_group_form import MessageTemplateForm
from apps.messaging.models import MessageTemplate, SatisfactionReview, ScheduledOutboundMessage
from apps.messaging.rendering import render_message_template
from apps.scheduling.models import Appointment, AppointmentStatus
from apps.workorder.models import WorkOrder, WorkOrderStatus
from apps.workshops.models.workshops import Workshop
from django.test import Client


def create_workshop(*, suffix: int = 1) -> Workshop:
    return Workshop.objects.create(
        name=f"Oficina Avaliacoes {suffix}",
        cnpj=f"11.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


class MessageTemplateTypeTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=1)

    def test_activating_typed_template_deactivates_previous(self) -> None:
        first = MessageTemplate.objects.create(
            workshop=self.workshop,
            name="Oleo 1",
            message="Troca %%placa%%",
            template_type=MessageTemplate.TemplateType.OIL_CHANGE,
            is_active=True,
        )
        form = MessageTemplateForm(
            data={
                "name": "Oleo 2",
                "template_type": MessageTemplate.TemplateType.OIL_CHANGE,
                "message": "Nova troca %%placa%%",
                "is_active": True,
            },
            workshop=self.workshop,
        )
        self.assertTrue(form.is_valid(), form.errors)
        second = form.save()
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)
        self.assertEqual(second.template_type, MessageTemplate.TemplateType.OIL_CHANGE)

    def test_multiple_generic_templates_can_be_active(self) -> None:
        MessageTemplate.objects.create(
            workshop=self.workshop,
            name="Gen 1",
            message="Oi",
            template_type=MessageTemplate.TemplateType.GENERIC,
            is_active=True,
        )
        form = MessageTemplateForm(
            data={
                "name": "Gen 2",
                "template_type": MessageTemplate.TemplateType.GENERIC,
                "message": "Oi 2",
                "is_active": True,
            },
            workshop=self.workshop,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(
            MessageTemplate.objects.filter(
                workshop=self.workshop,
                template_type=MessageTemplate.TemplateType.GENERIC,
                is_active=True,
            ).count(),
            2,
        )


class TypedAlertTemplateTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=2)
        self.customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Alerta",
            cpf_or_cnpj="12345678901",
            email="alerta@example.com",
            phone="+5511988887777",
            accepts_messages=True,
        )
        self.vehicle = Vehicle.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            plate="ABC1D23",
            brand="VW",
            model="Gol",
            year_fabrication="2018",
            year_model="2019",
            color="Prata",
            next_oil_change_date=timezone.localdate() + timedelta(days=10),
        )

    def test_oil_alert_uses_active_template(self) -> None:
        MessageTemplate.objects.create(
            workshop=self.workshop,
            name="Oleo Ativo",
            message="Ola %%nome%% placa %%placa%%",
            template_type=MessageTemplate.TemplateType.OIL_CHANGE,
            is_active=True,
        )
        with patch(
            "apps.messaging.application.services.oil_change_alert.notification_run_at_for_vehicle",
            return_value=timezone.now() + timedelta(days=1),
        ):
            scheduled = sync_oil_change_alert_schedule(self.vehicle)
        self.assertIsNotNone(scheduled)
        assert scheduled is not None
        self.assertIn("Cliente Alerta", scheduled.message)
        self.assertIn("ABC1D23", scheduled.message)

    def test_oil_alert_skips_without_template(self) -> None:
        with patch(
            "apps.messaging.application.services.oil_change_alert.notification_run_at_for_vehicle",
            return_value=timezone.now() + timedelta(days=1),
        ):
            scheduled = sync_oil_change_alert_schedule(self.vehicle)
        self.assertIsNone(scheduled)

    def test_appointment_alert_uses_active_template(self) -> None:
        MessageTemplate.objects.create(
            workshop=self.workshop,
            name="Agenda Ativa",
            message="Oi %%nome%% em %%data_agendamento%% %%hora_agendamento%%",
            template_type=MessageTemplate.TemplateType.APPOINTMENT,
            is_active=True,
        )
        starts = timezone.now() + timedelta(days=2)
        appointment = Appointment.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            title="Revisao",
            starts_at=starts,
            ends_at=starts + timedelta(hours=1),
            status=AppointmentStatus.SCHEDULED,
            alert_customer=True,
            alert_lead_time=60,
        )
        scheduled = sync_appointment_alert_schedule(appointment)
        self.assertIsNotNone(scheduled)
        assert scheduled is not None
        self.assertIn("Cliente Alerta", scheduled.message)
        self.assertIn(timezone.localtime(starts).strftime("%d/%m/%Y"), scheduled.message)


class BirthdayAlertTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=3)
        today = timezone.localdate()
        self.customer = Customer.objects.create(
            workshop=self.workshop,
            name="Aniversariante",
            cpf_or_cnpj="12345678902",
            email="niver@example.com",
            phone="+5511977776666",
            birth_date=date(1990, today.month, today.day),
            is_active=True,
            accepts_messages=True,
        )
        MessageTemplate.objects.create(
            workshop=self.workshop,
            name="Niver",
            message="Feliz aniversario %%nome%% da %%nome_oficina%%",
            template_type=MessageTemplate.TemplateType.BIRTHDAY,
            is_active=True,
        )

    def test_enqueue_birthday_once_per_year(self) -> None:
        created = enqueue_birthday_alerts_for_day()
        self.assertEqual(created, 1)
        created_again = enqueue_birthday_alerts_for_day()
        self.assertEqual(created_again, 0)
        row = ScheduledOutboundMessage.objects.get(source=ScheduledOutboundMessage.Source.BIRTHDAY_ALERT)
        self.assertIn("Aniversariante", row.message)
        self.assertIn(self.workshop.name, row.message)


class SatisfactionSurveyTests(TestCase):
    def setUp(self) -> None:
        self.workshop = create_workshop(suffix=4)
        self.workshop.satisfaction_survey_enabled = True
        self.workshop.satisfaction_survey_delay_days = 2
        self.workshop.google_review_url = "https://maps.google.com/?q=oficina"
        self.workshop.google_review_min_rating = 4
        self.workshop.save()
        self.customer = Customer.objects.create(
            workshop=self.workshop,
            name="Cliente Review",
            cpf_or_cnpj="12345678903",
            email="review@example.com",
            phone="+5511966665555",
            accepts_messages=True,
        )
        self.vehicle = Vehicle.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            plate="XYZ9A88",
            brand="Fiat",
            model="Uno",
            year_fabrication="2015",
            year_model="2015",
            color="Branco",
        )
        self.budget = Budget.objects.create(
            workshop=self.workshop,
            customer=self.customer,
            vehicle=self.vehicle,
            entry_date=timezone.localdate(),
        )
        self.workorder = WorkOrder.objects.create(
            workshop=self.workshop,
            budget=self.budget,
            status=WorkOrderStatus.APPROVED,
            delivered_at=timezone.now(),
        )

    def test_schedule_uses_fixed_message_and_delay(self) -> None:
        review = schedule_satisfaction_survey_for_workorder(self.workorder)
        self.assertIsNotNone(review)
        assert review is not None
        assert review.scheduled_message is not None
        self.assertIn("Cliente Review", review.scheduled_message.message)
        self.assertIn(self.workshop.name, review.scheduled_message.message)
        self.assertIn(f"/review/{review.public_token}", review.scheduled_message.message)
        expected_run = self.workorder.delivered_at + timedelta(days=2)
        assert self.workorder.delivered_at is not None
        self.assertEqual(review.scheduled_message.run_at, expected_run)

    def test_schedule_immediate_toggle_uses_now_outside_production(self) -> None:
        from django.test import override_settings

        self.workshop.satisfaction_survey_send_immediately = True
        self.workshop.save(update_fields=["satisfaction_survey_send_immediately"])
        before = timezone.now()
        with override_settings(ENVIRONMENT="development"):
            review = schedule_satisfaction_survey_for_workorder(self.workorder)
        after = timezone.now()
        self.assertIsNotNone(review)
        assert review is not None
        assert review.scheduled_message is not None
        self.assertGreaterEqual(review.scheduled_message.run_at, before)
        self.assertLessEqual(review.scheduled_message.run_at, after)

    def test_schedule_immediate_toggle_ignored_in_production(self) -> None:
        from django.test import override_settings

        self.workshop.satisfaction_survey_send_immediately = True
        self.workshop.save(update_fields=["satisfaction_survey_send_immediately"])
        with override_settings(ENVIRONMENT="production"):
            review = schedule_satisfaction_survey_for_workorder(self.workorder)
        self.assertIsNotNone(review)
        assert review is not None
        assert review.scheduled_message is not None
        assert self.workorder.delivered_at is not None
        self.assertEqual(review.scheduled_message.run_at, self.workorder.delivered_at + timedelta(days=2))

    def test_public_review_shows_google_cta_when_rating_meets_threshold(self) -> None:
        review = schedule_satisfaction_survey_for_workorder(self.workorder)
        assert review is not None
        client = Client()
        url = reverse("public_satisfaction_review", kwargs={"token": review.public_token})
        response = client.post(url, data={"rating": "5", "comment": "Otimo"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Avaliar no Google")
        self.assertContains(response, self.workshop.google_review_url)
        review.refresh_from_db()
        self.assertEqual(review.status, SatisfactionReview.Status.SUBMITTED)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, "Otimo")
        self.assertTrue(review.google_cta_shown)

    def test_detail_modal_shows_rating_and_comment(self) -> None:
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory

        from apps.accounts.models import Account
        from apps.collaborators.models import WorkshopMember
        from apps.iam.models import WorkshopRole
        from apps.messaging.presentation.views.satisfaction_review_views import SatisfactionReviewDetailModalView

        review = schedule_satisfaction_survey_for_workorder(self.workorder)
        assert review is not None
        review.rating = 4
        review.comment = "Atendimento excelente e rápido."
        review.status = SatisfactionReview.Status.SUBMITTED
        review.submitted_at = timezone.now()
        review.save(update_fields=["rating", "comment", "status", "submitted_at", "atualizado_em"])

        User = get_user_model()
        account = Account.objects.create(name="Conta Modal Review")
        user = User.objects.create_user(username="review-modal-user", password="secret", cpf="39053344705")
        user.account = account
        user.save(update_fields=["account"])
        self.workshop.account = account
        self.workshop.save(update_fields=["account"])
        role = WorkshopRole.objects.create(account=account, name="Diretor")
        WorkshopMember.objects.create(user=user, workshop=self.workshop, role=role, is_active=True)

        request = RequestFactory().get(f"/messaging/reviews/{review.pk}/detail/")
        request.user = user
        request.session = {"active_workshop_id": self.workshop.pk}
        view = SatisfactionReviewDetailModalView()
        view.setup(request, pk=review.pk)
        view.workshop = self.workshop
        view.request = request
        response = view.get(request, pk=review.pk)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("4/5", content)
        self.assertIn("Atendimento excelente e rápido.", content)

    def test_public_review_hides_google_cta_below_threshold(self) -> None:
        review = schedule_satisfaction_survey_for_workorder(self.workorder)
        assert review is not None
        client = Client()
        url = reverse("public_satisfaction_review", kwargs={"token": review.public_token})
        response = client.post(url, data={"rating": "2", "comment": ""})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Avaliar no Google")
        review.refresh_from_db()
        self.assertFalse(review.google_cta_shown)

    def test_fixed_message_constant_contains_expected_tokens(self) -> None:
        self.assertIn("%%nome%%", SATISFACTION_SURVEY_MESSAGE)
        self.assertIn("%%nome_oficina%%", SATISFACTION_SURVEY_MESSAGE)
        self.assertIn("%%link-avaliacao%%", SATISFACTION_SURVEY_MESSAGE)
        rendered = render_message_template(
            SATISFACTION_SURVEY_MESSAGE,
            customer=self.customer,
            workshop=self.workshop,
            extras={"link-avaliacao": "https://example.com/review/abc"},
        )
        self.assertIn("Cliente Review", rendered)
        self.assertIn(self.workshop.name, rendered)
        self.assertIn("https://example.com/review/abc", rendered)


class SatisfactionReviewListScopedTests(TestCase):
    def test_list_filters_by_active_workshop(self) -> None:
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory

        from apps.accounts.models import Account
        from apps.collaborators.models import WorkshopMember
        from apps.iam.models import WorkshopRole
        from apps.messaging.presentation.views.satisfaction_review_views import SatisfactionReviewListView

        User = get_user_model()
        account = Account.objects.create(name="Conta Reviews")
        user = User.objects.create_user(username="review-user", password="secret", cpf="52998224725")
        user.account = account
        user.save(update_fields=["account"])

        workshop_a = create_workshop(suffix=5)
        workshop_a.account = account
        workshop_a.save(update_fields=["account"])
        workshop_b = create_workshop(suffix=6)
        workshop_b.account = account
        workshop_b.save(update_fields=["account"])

        role = WorkshopRole.objects.create(account=account, name="Diretor")
        WorkshopMember.objects.create(user=user, workshop=workshop_a, role=role, is_active=True)
        WorkshopMember.objects.create(user=user, workshop=workshop_b, role=role, is_active=True)

        customer_a = Customer.objects.create(
            workshop=workshop_a,
            name="Cliente A",
            cpf_or_cnpj="12345678904",
            email="a@example.com",
            phone="+5511955554444",
        )
        customer_b = Customer.objects.create(
            workshop=workshop_b,
            name="Cliente B",
            cpf_or_cnpj="12345678905",
            email="b@example.com",
            phone="+5511944443333",
        )
        budget_a = Budget.objects.create(workshop=workshop_a, customer=customer_a, entry_date=timezone.localdate())
        budget_b = Budget.objects.create(workshop=workshop_b, customer=customer_b, entry_date=timezone.localdate())
        wo_a = WorkOrder.objects.create(workshop=workshop_a, budget=budget_a)
        wo_b = WorkOrder.objects.create(workshop=workshop_b, budget=budget_b)
        SatisfactionReview.objects.create(workshop=workshop_a, customer=customer_a, workorder=wo_a)
        SatisfactionReview.objects.create(workshop=workshop_b, customer=customer_b, workorder=wo_b)

        request = RequestFactory().get("/messaging/reviews/")
        request.user = user
        request.session = {"active_workshop_id": workshop_a.pk}
        view = SatisfactionReviewListView()
        view.setup(request)
        view.workshop = workshop_a
        view.request = request
        queryset = view.get_queryset()
        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.first().customer.name, customer_a.name)
