from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from djmoney.money import Money

from apps.accounts.models import Account
from apps.collaborators.models import WorkshopMember
from apps.iam.utils import get_or_create_director_role
from apps.workshops.forms.workshop_costs import WorkshopCostForm
from apps.workshops.models.workshop_costs import WorkshopCost
from apps.workshops.models.workshops import Workshop
from apps.workshops.util.monthly_costs import create_default_monthly_costs

User = get_user_model()


class WorkshopCostProfitabilityTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Profitability")
        self.user = User.objects.create_user(username="director_prof", password="secret", cpf="11122233344")
        self.user.account = self.account
        self.user.save(update_fields=["account"])

        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Profitability",
            cnpj="99.888.777/0001-11",
            phone="+5511777777777",
            address="Rua Profit, 100",
        )
        role = get_or_create_director_role(account=self.account)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)

        create_default_monthly_costs(workshop=self.workshop)
        self.client = Client()
        self.client.login(username="director_prof", password="secret")

    def test_calculate_view_updates_multiplier_when_profit_target_changes(self):
        url = reverse("workshops:workshop_cost_calculate")
        post_data = {
            "month": 8,
            "year": 2026,
            "mechanic_quantity": 2,
            "work_hours_per_day": "08:00:00",
            "work_days_per_month": 22,
            "productivity_average": "0.60",
            "card_rate": "0.00",
            "tax_rate": "0.00",
            "profit_margin": "0.00",
            "commission_rate": "0.00",
            "risk_coefficient": "1.00",
            "parts_purchase_cap_0": "10000.00",
            "parts_purchase_cap_1": "BRL",
            "freight_cost_0": "0.00",
            "freight_cost_1": "BRL",
            "third_party_service_cap_0": "0.00",
            "third_party_service_cap_1": "BRL",
            "profit_target_0": "20000.00",
            "profit_target_1": "BRL",
        }

        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("Metas e Indicadores", content)
        # Gross revenue = 0 (monthly costs) + 20000 (profit) + 10000 (total_value) = 30000. Multiplier = 30000 / 10000 = 3.0
        self.assertIn("3", content)

    def test_form_validation_blocks_multiplier_below_3(self):
        data = {
            "month": 8,
            "year": 2026,
            "mechanic_quantity": 1,
            "work_hours_per_day": "08:00:00",
            "work_days_per_month": 22,
            "productivity_average": "0.60",
            "parts_purchase_cap_0": "10000.00",
            "parts_purchase_cap_1": "BRL",
            "profit_target_0": "5000.00",  # Total = 10000, Gross revenue target = 15000, Multiplier = 1.5 (< 3.0)
            "profit_target_1": "BRL",
        }
        form = WorkshopCostForm(data, workshop=self.workshop)
        self.assertFalse(form.is_valid())
        self.assertIn("profitability_multiplier", form.errors)
        self.assertIn(
            "O Multiplicador de Lucratividade não pode ser menor que 3,0",
            form.errors["profitability_multiplier"][0],
        )

    def test_form_validation_allows_multiplier_3_or_above(self):
        data = {
            "month": 8,
            "year": 2026,
            "mechanic_quantity": 1,
            "work_hours_per_day": "08:00:00",
            "work_days_per_month": 22,
            "productivity_average": "0.60",
            "parts_purchase_cap_0": "10000.00",
            "parts_purchase_cap_1": "BRL",
            "profit_target_0": "20000.00",  # Total = 10000, Gross revenue target = 30000, Multiplier = 3.0
            "profit_target_1": "BRL",
        }
        form = WorkshopCostForm(data, workshop=self.workshop)
        self.assertTrue(form.is_valid(), form.errors)
