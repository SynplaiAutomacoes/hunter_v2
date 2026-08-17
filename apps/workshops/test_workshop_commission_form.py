from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.collaborators.models import WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.workshops.forms.workshops import WorkshopCommissionSectionForm
from apps.workshops.models.workshop_commission import WorkshopCommissionSettings
from apps.workshops.models.workshops import Workshop

User = get_user_model()


def _create_workshop(*, account: Account | None, suffix: int) -> Workshop:
    return Workshop.objects.create(
        account=account,
        name=f"Oficina Comissao {suffix}",
        cnpj=f"31.222.333/0001-{suffix:02d}",
        phone="+5511999999999",
        address="Rua Teste, 123",
    )


class WorkshopCommissionSectionFormTests(TestCase):
    def test_save_creates_settings_when_enabled_with_percentage(self) -> None:
        account = Account.objects.create(name="Conta Comissao Form 1")
        workshop = _create_workshop(account=account, suffix=1)

        form = WorkshopCommissionSectionForm(
            data={
                "workorder_commission_enabled": "on",
                "workorder_commission_percentage": "0.050000",
            },
            workshop=workshop,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        settings = WorkshopCommissionSettings.objects.get(workshop=workshop)
        self.assertTrue(settings.workorder_commission_enabled)
        self.assertEqual(settings.workorder_commission_percentage, Decimal("0.050000"))

    def test_requires_percentage_when_enabled(self) -> None:
        account = Account.objects.create(name="Conta Comissao Form 2")
        workshop = _create_workshop(account=account, suffix=2)

        form = WorkshopCommissionSectionForm(
            data={
                "workorder_commission_enabled": "on",
                "workorder_commission_percentage": "",
            },
            workshop=workshop,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("workorder_commission_percentage", form.errors)

    def test_save_updates_existing_settings(self) -> None:
        account = Account.objects.create(name="Conta Comissao Form 3")
        workshop = _create_workshop(account=account, suffix=3)
        settings = WorkshopCommissionSettings.objects.create(
            workshop=workshop,
            workorder_commission_enabled=True,
            workorder_commission_percentage=Decimal("0.050000"),
        )

        form = WorkshopCommissionSectionForm(
            data={
                "workorder_commission_enabled": "on",
                "workorder_commission_percentage": "0.080000",
            },
            workshop=workshop,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        settings.refresh_from_db()
        self.assertEqual(settings.workorder_commission_percentage, Decimal("0.080000"))


class WorkshopCommissionUpdateViewTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Comissao View")
        self.user = User.objects.create_user(username="director_comissao", password="secret", cpf="91526473012")
        self.user.account = self.account
        self.user.save(update_fields=["account"])

        self.workshop = _create_workshop(account=self.account, suffix=4)
        role = get_or_create_director_role(account=self.account)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)

        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.url = reverse("workshops:update", kwargs={"pk": self.workshop.pk})

    def test_update_page_renders_commission_tab(self) -> None:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "comissao")
        self.assertContains(response, "workorder_commission_percentage")

    def test_post_saves_commission_settings(self) -> None:
        response = self.client.post(
            self.url,
            {
                "tab": "comissao",
                "nf_tab": "",
                "workorder_commission_enabled": "on",
                "workorder_commission_percentage": "0.050000",
            },
        )
        self.assertEqual(response.status_code, 302)
        settings = WorkshopCommissionSettings.objects.get(workshop=self.workshop)
        self.assertTrue(settings.workorder_commission_enabled)
        self.assertEqual(settings.workorder_commission_percentage, Decimal("0.050000"))