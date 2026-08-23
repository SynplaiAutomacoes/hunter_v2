from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.catalog.forms.kits import KitForm
from apps.collaborators.models import WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class KitFormLayoutTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Kit Layout")
        self.user = User.objects.create_user(username="kit-layout-user", password="secret", cpf="12345678909")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Kit Layout",
            cnpj="12.345.678/0001-93",
            phone="+5511999999997",
            address="Rua Kit Layout, 1",
        )
        role = get_or_create_director_role(account=self.account)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_kit_form_layout_builds_without_payload_nameerror(self) -> None:
        form = KitForm(workshop=self.workshop)
        layout = form.get_layout()
        self.assertIsNotNone(layout)

    def test_kit_create_page_renders_from_budget_next_url(self) -> None:
        budget_return_url = "/budget/1/edit/?step=4"
        response = self.client.get(reverse("catalog:kits_create"), {"next": budget_return_url})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Novo Kit")
