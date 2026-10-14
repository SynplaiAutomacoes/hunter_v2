from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Account
from apps.collaborators.models import WorkshopMember
from apps.customer.models import Customer, Vehicle
from apps.iam.models import WorkshopRole
from apps.workshops.models.workshops import Workshop


User = get_user_model()


class CustomerVehicleScopingTests(TestCase):
    def setUp(self) -> None:
        self.account = Account.objects.create(name="Conta Budget Scope")
        self.user = User.objects.create_user(username="budget-scope", password="secret", cpf="12345678901")
        self.user.account = self.account
        self.user.is_account_owner = True
        self.user.save(update_fields=["account", "is_account_owner"])

        self.workshop_a = Workshop.objects.create(
            account=self.account,
            name="Oficina A",
            cnpj="12.345.678/0001-90",
            phone="+5511999999991",
            address="Rua A, 1",
        )
        self.workshop_b = Workshop.objects.create(
            account=self.account,
            name="Oficina B",
            cnpj="12.345.678/0001-91",
            phone="+5511999999992",
            address="Rua B, 2",
        )
        role = WorkshopRole.objects.create(account=self.account, name="Diretor")
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop_a, role=role, is_active=True)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop_b, role=role, is_active=True)

        self.customer_a = Customer.objects.create(
            workshop=self.workshop_a,
            name="Cliente A",
            cpf_or_cnpj="52998224725",
            email="a@example.invalid",
        )
        self.customer_b = Customer.objects.create(
            workshop=self.workshop_b,
            name="Cliente B",
            cpf_or_cnpj="39053344725",
            email="b@example.invalid",
        )
        self.vehicle_b = Vehicle.objects.create(
            workshop=self.workshop_b,
            customer=self.customer_b,
            plate="ABC1D23",
            brand="Fiat",
            model="Uno",
            year_fabrication="2015",
            year_model="2015",
            color="Prata",
            km=10000,
        )

    def test_anonymous_is_redirected(self) -> None:
        url = reverse("budget:customer-detail")
        response = self.client.get(url, {"customer": self.customer_a.pk})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_customer_from_other_workshop_returns_404(self) -> None:
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop_a.pk
        session.save()

        url = reverse("budget:customer-detail")
        response = self.client.get(url, {"customer": self.customer_b.pk})
        self.assertEqual(response.status_code, 404)

    def test_vehicle_from_other_workshop_returns_404(self) -> None:
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop_a.pk
        session.save()

        url = reverse("budget:vehicle-detail")
        response = self.client.get(url, {"vehicle": self.vehicle_b.pk})
        self.assertEqual(response.status_code, 404)

    def test_customer_from_active_workshop_ok(self) -> None:
        self.client.force_login(self.user)
        session = self.client.session
        session["active_workshop_id"] = self.workshop_a.pk
        session.save()

        url = reverse("budget:customer-detail")
        response = self.client.get(url, {"customer": self.customer_a.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cliente a")
