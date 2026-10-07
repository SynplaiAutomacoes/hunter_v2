from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.accounts.models import Account
from apps.billing.models import AccountSubscription, SubscriptionPlan, SubscriptionStatus
from apps.collaborators.models import WorkshopMember
from apps.core.presentation.navigation import get_navbar_menus
from apps.iam.utils import get_or_create_director_role
from apps.workshops.models.workshops import Workshop

User = get_user_model()


class BillingNavigationTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.account = Account.objects.create(name="Conta Nav Billing")
        self.user = User.objects.create_user(username="nav-billing", password="secret", cpf="52998224725")
        self.user.account = self.account
        self.user.is_account_owner = True
        self.user.save(update_fields=["account", "is_account_owner"])
        self.account.owner = self.user
        self.account.save(update_fields=["owner"])
        self.workshop = Workshop.objects.create(
            account=self.account,
            name="Oficina Nav Billing",
            cnpj="12.345.678/0001-90",
            phone="+5511999999999",
            address="Rua Nav, 1",
        )
        role = get_or_create_director_role(account=self.account)
        WorkshopMember.objects.create(user=self.user, workshop=self.workshop, role=role, is_active=True)

    def _request(self):
        request = self.factory.get("/budget/")
        request.user = self.user
        SessionMiddleware(lambda _r: HttpResponse()).process_request(request)
        request.session["active_workshop_id"] = self.workshop.pk
        request.session.save()
        return request

    def test_basic_plan_hides_finance_and_stock(self) -> None:
        AccountSubscription.objects.create(
            account=self.account,
            plan=SubscriptionPlan.BASIC,
            status=SubscriptionStatus.ACTIVE,
        )
        menus = get_navbar_menus(self._request())
        labels = {menu["label"] for menu in menus}
        self.assertIn("Orçamentos", labels)
        self.assertNotIn("Financeiro", labels)
        self.assertNotIn("Estoque", labels)
        self.assertNotIn("Ordens de Serviço", labels)
        self.assertNotIn("Agendamentos", labels)

    def test_full_plan_shows_finance_and_stock(self) -> None:
        AccountSubscription.objects.create(
            account=self.account,
            plan=SubscriptionPlan.FULL,
            status=SubscriptionStatus.ACTIVE,
        )
        menus = get_navbar_menus(self._request())
        labels = {menu["label"] for menu in menus}
        self.assertIn("Financeiro", labels)
        self.assertIn("Estoque", labels)
        self.assertIn("Ordens de Serviço", labels)
