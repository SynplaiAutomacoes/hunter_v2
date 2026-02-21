from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Account, User
from apps.finance.services.webmania_b2b import WebmaniaB2BServiceError
from apps.workshops.forms.workshops import WorkshopForm
from apps.workshops.models.workshops import Workshop


class WorkshopFormTests(TestCase):
    def test_create_form_uf_starts_empty_and_uses_placeholder(self) -> None:
        form = WorkshopForm()

        self.assertEqual(form.initial["uf"], "")
        self.assertEqual(form.fields["uf"].widget.attrs["placeholder"], "SP")


class WorkshopCreateViewTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="owner", password="123", cpf="12345678909")
        self.account = Account.objects.create(name="Conta Teste", owner=self.user)
        self.user.account = self.account
        self.user.is_account_owner = True
        self.user.save(update_fields=["account", "is_account_owner"])
        self.client.force_login(self.user)

    def _valid_payload(self) -> dict[str, str]:
        return {
            "name": "Oficina Nova",
            "cnpj": "11.222.333/0001-81",
            "phone": "+5511999999999",
            "address": "Rua das Oficinas, 123",
            "uf": "SP",
            "is_active": "on",
        }

    def test_create_workshop_calls_webmania_provisioning(self) -> None:
        with patch("apps.workshops.views.workshops.provision_webmania_company_for_workshop") as provision_mock, patch("apps.workshops.views.workshops.create_default_monthly_costs"):
            response = self.client.post(reverse("workshops:create"), data=self._valid_payload())

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Workshop.objects.count(), 1)
        provision_mock.assert_called_once()

    def test_create_workshop_rolls_back_when_webmania_fails(self) -> None:
        with (
            patch(
                "apps.workshops.views.workshops.provision_webmania_company_for_workshop",
                side_effect=WebmaniaB2BServiceError("Erro ao criar empresa na Webmania"),
            ),
            patch("apps.workshops.views.workshops.create_default_monthly_costs") as monthly_mock,
        ):
            response = self.client.post(reverse("workshops:create"), data=self._valid_payload())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Workshop.objects.count(), 0)
        monthly_mock.assert_not_called()
