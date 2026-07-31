from __future__ import annotations

from datetime import time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.collaborators.models import WorkshopMember
from apps.iam.models import WorkshopRole
from apps.workshops.forms.workshops import WorkshopAssistantVirtualSectionForm
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class WorkshopAssistantVirtualFormTests(TestCase):
    def test_save_persists_weekdays_and_times(self) -> None:
        workshop = Workshop.objects.create(
            name="Oficina Hours Form",
            cnpj="12.345.678/0001-77",
            phone="+5511999999999",
            address="Rua A, 123",
        )
        form = WorkshopAssistantVirtualSectionForm(
            data={
                "weekdays": ["0", "2", "4"],
                "outbound_business_start_time": "09:30:00",
                "outbound_business_end_time": "17:00:00",
                "satisfaction_survey_enabled": False,
                "satisfaction_survey_delay_days": 1,
                "google_review_url": "",
                "google_review_min_rating": 4,
            },
            instance=workshop,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        workshop.refresh_from_db()
        self.assertEqual(workshop.outbound_business_weekdays, "0,2,4")
        self.assertEqual(workshop.outbound_business_start_time, time(9, 30))
        self.assertEqual(workshop.outbound_business_end_time, time(17, 0))
        self.assertTrue(workshop.outbound_business_hours_enabled)

    def test_requires_weekdays(self) -> None:
        workshop = Workshop.objects.create(
            name="Oficina Hours Invalid",
            cnpj="12.345.678/0001-78",
            phone="+5511999999999",
            address="Rua A, 123",
        )
        form = WorkshopAssistantVirtualSectionForm(
            data={
                "weekdays": [],
                "outbound_business_start_time": "08:00:00",
                "outbound_business_end_time": "18:00:00",
                "satisfaction_survey_delay_days": 1,
                "google_review_min_rating": 4,
            },
            instance=workshop,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("weekdays", form.errors)

    def test_end_time_must_be_greater_than_start(self) -> None:
        workshop = Workshop.objects.create(
            name="Oficina Hours Range",
            cnpj="12.345.678/0001-79",
            phone="+5511999999999",
            address="Rua A, 123",
        )
        form = WorkshopAssistantVirtualSectionForm(
            data={
                "weekdays": ["0"],
                "outbound_business_start_time": "18:00:00",
                "outbound_business_end_time": "08:00:00",
                "satisfaction_survey_delay_days": 1,
                "google_review_min_rating": 4,
            },
            instance=workshop,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("outbound_business_end_time", form.errors)

    def test_rejects_invalid_clock_time(self) -> None:
        workshop = Workshop.objects.create(
            name="Oficina Hours Bad",
            cnpj="12.345.678/0001-76",
            phone="+5511999999999",
            address="Rua A, 123",
        )
        form = WorkshopAssistantVirtualSectionForm(
            data={
                "weekdays": ["0"],
                "outbound_business_start_time": "25:00:00",
                "outbound_business_end_time": "18:00:00",
                "satisfaction_survey_delay_days": 1,
                "google_review_min_rating": 4,
            },
            instance=workshop,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("outbound_business_start_time", form.errors)

    def test_allows_immediate_toggle_outside_production(self) -> None:
        from django.test import override_settings

        workshop = Workshop.objects.create(
            name="Oficina Immediate Delay",
            cnpj="12.345.678/0001-75",
            phone="+5511999999999",
            address="Rua A, 123",
        )
        with override_settings(ENVIRONMENT="development"):
            form = WorkshopAssistantVirtualSectionForm(
                data={
                    "weekdays": ["0"],
                    "outbound_business_start_time": "08:00:00",
                    "outbound_business_end_time": "18:00:00",
                    "satisfaction_survey_enabled": True,
                    "satisfaction_survey_delay_days": 3,
                    "satisfaction_survey_send_immediately": True,
                    "google_review_url": "",
                    "google_review_min_rating": 4,
                },
                instance=workshop,
            )
            self.assertTrue(form.is_valid(), form.errors)
            self.assertIn("satisfaction_survey_send_immediately", form.fields)
            form.save()
        workshop.refresh_from_db()
        self.assertTrue(workshop.satisfaction_survey_send_immediately)
        self.assertEqual(workshop.satisfaction_survey_delay_days, 3)

    def test_hides_immediate_toggle_in_production(self) -> None:
        from django.test import override_settings

        workshop = Workshop.objects.create(
            name="Oficina Prod Delay",
            cnpj="12.345.678/0001-74",
            phone="+5511999999999",
            address="Rua A, 123",
            satisfaction_survey_send_immediately=True,
        )
        with override_settings(ENVIRONMENT="production"):
            form = WorkshopAssistantVirtualSectionForm(
                data={
                    "weekdays": ["0"],
                    "outbound_business_start_time": "08:00:00",
                    "outbound_business_end_time": "18:00:00",
                    "satisfaction_survey_enabled": True,
                    "satisfaction_survey_delay_days": 2,
                    "google_review_url": "",
                    "google_review_min_rating": 4,
                },
                instance=workshop,
            )
            self.assertNotIn("satisfaction_survey_send_immediately", form.fields)
            self.assertTrue(form.is_valid(), form.errors)
            form.save()
        workshop.refresh_from_db()
        self.assertFalse(workshop.satisfaction_survey_send_immediately)

    def test_weekdays_choices_start_on_sunday(self) -> None:
        from apps.workshops.forms.workshops import WEEKDAY_CHOICES

        self.assertEqual([day for day, _label in WEEKDAY_CHOICES], ["6", "0", "1", "2", "3", "4", "5"])
        self.assertEqual(WEEKDAY_CHOICES[0][1], "Dom")
        self.assertEqual(WEEKDAY_CHOICES[-1][1], "Sáb")


class WorkshopAssistantVirtualTabTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Hours")
        self.user = User.objects.create_user(username="hours-user", password="secret", cpf="12345678901")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Hours UI",
            cnpj="12.345.678/0001-80",
            phone="+5511999999999",
            address="Rua A, 123",
        )
        role = WorkshopRole.objects.create(account=self.account, name="Diretor")
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_get_renders_assistant_virtual_tab(self) -> None:
        url = reverse("workshops:update", kwargs={"pk": self.workshop.pk})
        response = self.client.get(url, {"tab": "assistente_virtual"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assistente Virtual")
        self.assertContains(response, "Configure o seu assistente virtual e horário de funcionamento.")
        self.assertContains(response, "Horário de funcionamento")
        self.assertNotContains(response, "Respeitar")

    def test_post_persists_assistant_virtual_hours(self) -> None:
        url = reverse("workshops:update", kwargs={"pk": self.workshop.pk})
        response = self.client.post(
            url,
            data={
                "tab": "assistente_virtual",
                "nf_tab": "nfe",
                "weekdays": ["1", "3", "5"],
                "outbound_business_start_time": "10:15:00",
                "outbound_business_end_time": "19:00:00",
                "satisfaction_survey_enabled": "on",
                "satisfaction_survey_delay_days": 2,
                "google_review_url": "https://g.page/r/example",
                "google_review_min_rating": 5,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.outbound_business_weekdays, "1,3,5")
        self.assertEqual(self.workshop.outbound_business_start_time, time(10, 15))
        self.assertEqual(self.workshop.outbound_business_end_time, time(19, 0))
        self.assertTrue(self.workshop.satisfaction_survey_enabled)
        self.assertEqual(self.workshop.satisfaction_survey_delay_days, 2)
        self.assertEqual(self.workshop.google_review_url, "https://g.page/r/example")
        self.assertEqual(self.workshop.google_review_min_rating, 5)
