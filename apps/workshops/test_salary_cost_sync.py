from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from djmoney.money import Money

from apps.accounts.models import Account
from apps.collaborators.models import WorkshopCollaborator, WorkshopMember
from apps.collaborators.services import sync_collaborator_payroll
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.monthly_costs import MonthlyCost
from apps.workshops.models.workshop_costs import WorkshopCost, WorkshopCostItem
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import (
    MECHANIC_SALARY_MONTHLY_COST_NAME,
    TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME,
    create_default_monthly_costs,
)

User = get_user_model()


class WorkshopCostSyncSalaryItemsViewTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Sync Salary")
        self.user = User.objects.create_user(username="director_sync", password="secret", cpf="98765432100")
        self.user.account = self.account
        self.user.save(update_fields=["account"])

        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Sync Salary",
            cnpj="12.345.678/0001-91",
            phone="+5511888888888",
            address="Rua Sync, 10",
        )
        role = get_or_create_director_role(account=self.account)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)

        create_default_monthly_costs(workshop=self.workshop)
        self.workshop_cost = WorkshopCost.objects.create(
            workshop=self.workshop,
            year=2026,
            month=7,
            mechanic_quantity=1,
            work_days_per_month=22,
        )
        self.productive = WorkshopCollaborator.objects.create(
            workshop=self.workshop,
            name="Mecanico Sync",
            cpf="12345678909",
            birth_date=date(1990, 1, 1),
            salary=Money(4000, "BRL"),
            transport_allowance_daily=Money(20, "BRL"),
            admission_date=date(2025, 1, 1),
            collaborator_type=WorkshopCollaborator.CollaboratorType.PRODUCTIVE,
        )
        sync_collaborator_payroll(collaborator=self.productive, reference_date=date(2026, 7, 1), lock_reference=True)

        self.client = Client()
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop.pk
        session.save()

    def test_sync_salary_items_persists_and_returns_form_fields(self) -> None:
        response = self.client.post(
            reverse("workshops:workshop_cost_sync_salary_items"),
            {"month": 7, "year": 2026},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["synced"])

        mechanic_cost = MonthlyCost.objects.get(workshop=self.workshop, name=MECHANIC_SALARY_MONTHLY_COST_NAME)
        transport_cost = MonthlyCost.objects.get(workshop=self.workshop, name=TRANSPORT_ALLOWANCE_MONTHLY_COST_NAME)
        self.assertEqual(payload["fields"][f"cost_item_{mechanic_cost.pk}_0"], "4000.00")
        self.assertEqual(payload["fields"][f"cost_item_{transport_cost.pk}_0"], "440.00")

        mechanic_item = WorkshopCostItem.objects.get(workshop_cost=self.workshop_cost, monthly_cost=mechanic_cost)
        transport_item = WorkshopCostItem.objects.get(workshop_cost=self.workshop_cost, monthly_cost=transport_cost)
        self.assertEqual(mechanic_item.amount, Money("4000.00", "BRL"))
        self.assertEqual(transport_item.amount, Money("440.00", "BRL"))

    def test_sync_salary_items_without_workshop_cost_only_returns_fields(self) -> None:
        response = self.client.post(
            reverse("workshops:workshop_cost_sync_salary_items"),
            {"month": 8, "year": 2026},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["synced"])
        self.assertFalse(WorkshopCost.objects.filter(workshop=self.workshop, month=8, year=2026).exists())

        mechanic_cost = MonthlyCost.objects.get(workshop=self.workshop, name=MECHANIC_SALARY_MONTHLY_COST_NAME)
        self.assertEqual(payload["fields"][f"cost_item_{mechanic_cost.pk}_0"], "4000.00")
