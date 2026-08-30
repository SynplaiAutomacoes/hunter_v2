from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.collaborators.models import WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class DreFormValidationTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta DRE Form")
        self.user = User.objects.create_user(username="dre-form-user", password="secret", cpf="12345678906")
        self.user.account = self.account
        self.user.save(update_fields=["account"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina DRE Form",
            cnpj="12.345.678/0001-91",
            phone="+5511999999996",
            address="Rua DRE Form, 1",
        )
        role = get_or_create_director_role(account=self.account)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def _valid_query(self) -> dict[str, str]:
        return {
            "filial": str(self.workshop.pk),
            "data_inicial": "2026-01-01",
            "data_final": "2026-01-31",
            "tipo_data": "A",
        }

    def test_results_redirects_when_tipo_data_is_missing(self) -> None:
        query = self._valid_query()
        query.pop("tipo_data")

        response = self.client.get(reverse("finance:dre_results"), query)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("finance:dre_report"))

    def test_results_renders_when_tipo_data_is_selected(self) -> None:
        response = self.client.get(reverse("finance:dre_results"), self._valid_query())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Receita Bruta de Vendas e Serviços")

    def test_pdf_redirects_when_tipo_data_is_missing(self) -> None:
        query = self._valid_query()
        query.pop("tipo_data")

        response = self.client.get(reverse("finance:dre_pdf"), query)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("finance:dre_report"))

    def test_excel_redirects_when_tipo_data_is_missing(self) -> None:
        query = self._valid_query()
        query.pop("tipo_data")

        response = self.client.get(reverse("finance:dre_excel"), query)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("finance:dre_report"))
