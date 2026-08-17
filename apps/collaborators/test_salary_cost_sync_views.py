from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from djmoney.money import Money

from apps.accounts.models import Account
from apps.collaborators.models import WorkshopCollaborator, WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import MECHANIC_SALARY_MONTHLY_COST_NAME, create_default_monthly_costs

User = get_user_model()


class CollaboratorModalUpdateSyncFlagTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Collab Sync")
        self.user = User.objects.create_user(username="director_collab", password="secret", cpf="98765432101")
        self.user.account = self.account
        self.user.save(update_fields=["account"])

        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Collab Sync",
            cnpj="12.345.678/0001-92",
            phone="+5511777777777",
            address="Rua Collab, 10",
        )
        role = get_or_create_director_role(account=self.account)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)

        create_default_monthly_costs(workshop=self.workshop)
        self.workshop_cost = WorkshopCost.objects.create(
            workshop=self.workshop,
            year=date.today().year,
            month=date.today().month,
            mechanic_quantity=1,
            work_days_per_month=22,
        )
        self.collaborator = WorkshopCollaborator.objects.create(
            workshop=self.workshop,
            name="Mecanico Edit",
            cpf="40676429890",
            birth_date=date(1990, 1, 1),
            salary=Money(1000, "BRL"),
            transport_allowance_daily=Money(0, "BRL"),
            admission_date=date(2025, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
        )

        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

        self.url = reverse("collaborators:collaborator_update_modal", kwargs={"pk": self.collaborator.pk})
        self.base_payload = {
            "name": self.collaborator.name,
            "cpf": self.collaborator.cpf,
            "email": "",
            "phone": "",
            "birth_date": self.collaborator.birth_date.isoformat(),
            "position": "Mecanico",
            "collaborator_type": "P",
            "admission_date": self.collaborator.admission_date.isoformat(),
            "salary_0": "2500.00",
            "salary_1": "BRL",
        }

    def _mechanic_item_amount(self) -> Money | None:
        mechanic_cost = MonthlyCost.objects.get(workshop=self.workshop, name=MECHANIC_SALARY_MONTHLY_COST_NAME)
        item = WorkshopCostItem.objects.filter(workshop_cost=self.workshop_cost, monthly_cost=mechanic_cost).first()
        return item.amount if item is not None else None

    def test_modal_update_without_sync_flag_does_not_update_monthly_cost(self) -> None:
        response = self.client.post(self.url, {**self.base_payload, "sync_monthly_costs": "0"})
        self.assertEqual(response.status_code, 204)
        self.collaborator.refresh_from_db()
        self.assertEqual(self.collaborator.salary, Money("2500.00", "BRL"))
        self.assertIsNone(self._mechanic_item_amount())

    def test_modal_update_with_sync_flag_updates_monthly_cost(self) -> None:
        response = self.client.post(self.url, {**self.base_payload, "sync_monthly_costs": "1"})
        self.assertEqual(response.status_code, 204)
        self.collaborator.refresh_from_db()
        self.assertEqual(self.collaborator.salary, Money("2500.00", "BRL"))
        self.assertEqual(self._mechanic_item_amount(), Money("2500.00", "BRL"))

    def test_update_page_renders_commission_rules_formset(self) -> None:
        self.collaborator.receives_commission = True
        self.collaborator.save(update_fields=["receives_commission"])
        url = reverse("collaborators:collaborator_update", kwargs={"pk": self.collaborator.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id_commission_rules-TOTAL_FORMS')
        self.assertContains(response, "Regras de comissão")
